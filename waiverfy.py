#!/usr/bin/env python3

# Description: This script reads a yaml file and generates a waiver file based on the failed controls
# Usage: waiverfy.py <filename> <waiverfile>
# Version: 1.7
# Author: Joshua Mazgelis
# Depends on: PyYAML, Python3

import sys
import yaml
import datetime
import os
import tempfile

print("Welcome to the waiverfy script.")
print("This script will generate a waiver file based on the failed controls in a report.")

if len(sys.argv) < 3:
    print("Usage: waiverfy.py <filename> <waiverfile>")
    print("Example: waiverfy.py ./reports/report.yml ./waivers/waivers.yml")
    sys.exit(1)
reportfile = sys.argv[1]
waiverfile = sys.argv[2]

# Check if the report file exists
if not os.path.isfile(reportfile):
    print("Report file does not exist.")
else:
    print("Report file located.")

# The PyYAML library does not handle unknown tags by default.
# - raise ConstructorError(None, None, yaml.constructor.ConstructorError: could not determine a constructor for the tag '!ruby/object:FilterTable::ExceptionCatcher'
# This code adds a multi constructor that matches any tag starting with ! and simply returns an empty dictionary when such a tag is encountered. This effectively ignores these tags. 
# (Not working yet, but I did implement a workaround by striping the tag from the yaml file)
def ignore_unknown_tags(loader, tag_suffix, node):
    return {}
yaml.add_multi_constructor('!', ignore_unknown_tags)

# Open the report file and read the data
with open(reportfile, 'r') as file:
    report_data = file.read()

# Check if the report file contains strings that will cause an error
modified_report_data = report_data.replace('!ruby/object:FilterTable::ExceptionCatcher {}', '{}')

if modified_report_data != report_data:
    print("The report file contains strings that will cause an error. Using a modified file.")
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
        temp_file.write(modified_report_data)
        modified_reportfile = temp_file.name

    # Use the modified file for further processing
    reportfile = modified_reportfile

# Check if the report has any failed controls
print(f'Checking {reportfile} for failed controls...')

# with open(reportfile, 'r') as file:
#     data = yaml.safe_load(file)

with open(reportfile, 'r') as stream:
    data = yaml.safe_load(stream)

failed_controls = False
for profile in data[':profiles']:
    for control in profile[':controls']:
        for result in control[':results']:
            if result[':status'] == 'failed':
                failed_controls = True
                break
        if failed_controls:
            break
    if failed_controls:
        break

if not failed_controls:
    print("No failed controls found in the report. Exiting waiverfy script.")
    sys.exit(1)
else:
    print("Failed controls found in the report.")

print("Preparing waiver file...")

# Check if the waivers directory exists, if not create it
waivers_dir = os.path.dirname(waiverfile)
if waivers_dir:
    if not os.path.isdir(waivers_dir):
        os.makedirs(waivers_dir)

# Check if the waiver file already exists, if yes, prompt the user to overwrite it
if os.path.isfile(waiverfile):
    overwrite = input("The waiver file already exists. Do you want to overwrite it? (y/n): ")
    if overwrite.lower() != 'y':
        print("Exiting waiverfy script.")
        sys.exit(1)

expiration_options = {
    '90 days': datetime.date.today() + datetime.timedelta(days=90),
    '6 months': datetime.date.today() + datetime.timedelta(days=180),
    '12 months': datetime.date.today() + datetime.timedelta(days=365),
    '18 months': datetime.date.today() + datetime.timedelta(days=540),
    'custom date': None
}

print("Choose the default waiver expiration date:")
for i, option in enumerate(expiration_options.keys()):
    print(f"{i+1}. {option}")

choice = input("Enter the number corresponding to your choice [1]: ")
choice = int(choice) - 1 if choice else 0

expiration_choice = list(expiration_options.keys())[choice]

if expiration_choice == 'custom date':
    custom_date = input("Enter the custom expiration date (YYYY-MM-DD): ")
    try:
        expiration_date = datetime.datetime.strptime(custom_date, "%Y-%m-%d").date()
    except ValueError:
        print("Invalid date format. Attempting to fix...")
        try:
            expiration_date = datetime.datetime.strptime(custom_date, "%m-%d-%Y").date()
            print("Date format fixed.")
        except ValueError:
            print("Unable to fix date format. Using default expiration date of 90 days.")
            expiration_date = expiration_options['90 days']
else:
    expiration_date = expiration_options.get(expiration_choice)

if expiration_date is None:
    print("Invalid expiration date. Using default expiration date of 90 days.")
    expiration_date = expiration_options['90 days']

justification = "Under review by security team"
print(f"Default justification: \033[93m{justification}\033[0m")
update_justification = input("Do you want to update the justification? (y/n): ")
if update_justification.lower() == 'y':
    justification = input("Enter the new justification: ")

run_tests = input("Should InSpec run tests for waived controls? (y/n): ")
if run_tests.lower() != 'n':
    run_tests = "yes"
    print("InSpec will run tests for waived controls.")
else:
    run_tests = "no"
    print("InSpec will not run tests for waived controls.")

print(f'Generating waivers based on {reportfile}...')
# We will keep track of the number of waivers written
waiver_count = 0
profile_count = 0
control_count = 0
results_count = 0
results_count_failed = 0

with open(reportfile, 'r') as yamlreport:
    data = yaml.safe_load(yamlreport)

with open(waiverfile, 'w') as wf:
    wf.write("# This is an InSpec waiver file generated by the waiverfy script.\n")
    wf.write("# Originally generated from a report named: " + reportfile + "\n\n")
    for profile in data[':profiles']:        
        profile_count += 1
        print(f'Found Profile Name: {profile[":name"]}')
        print(f'Profile Title: {profile[":title"]}')
        wf.write(f'# Found Profile Name: {profile[":name"]}\n')
        wf.write(f'# Profile Title: {profile[":title"]}\n\n')
        for control in profile[':controls']:
            control_count += 1
            id = control[':id']
            title = control[':title']
            # Conditions can occur where a control has been executed and reported multiple times
            # To avoid creating duplicate waivers, we can keep track of the waivers we have already written
            # and skip writing a waiver if it has already been written for the control
            waivers_written = set()
            if not control.get(':results'):
                print(f'Warning: Control ID {id} has no results.')
                continue
            for result in control[':results']:
                results_count += 1
                status = result.get(':status')
                if status is None:
                    print(f'Warning: Control ID {id} has no status.')
                    continue
                print(f'Control ID: {id}, Status: {status}')
                if status == 'failed':
                    results_count_failed += 1
                    if id in waivers_written:
                        print(f'Waiver for Control ID: {id} already written to {waiverfile}')
                        continue  # Skip writing waiver if it has already been written
                    waivers_written.add(id)  # Add control ID to set of waivers written
                    # Write the waiver data to the file
                    wf.write(f'# Control Title: {title}\n')
                    wf.write(f'{id}:\n')
                    wf.write(f'  expiration_date: {expiration_date}\n')
                    wf.write(f'  justification: {justification}\n')
                    wf.write(f'  run: {run_tests}\n\n')
                    print(f'Waiver for Control ID: {id} written to {waiverfile}')
                    waiver_count += 1
    pass
                    # Sample of another way to write the waivers? 
                    # Would need good control over the formatting

                    # if status == 'failed':
                    #     waiver = {
                    #         'id': id,
                    #         'title': title,
                    #         'expiration_date': expiration_date.strftime("%Y-%m-%d"),
                    #         'justification': justification,
                    #         'run': 'yes'
                    #     }
                    #     waiver_data.append(waiver)

print()
print(f'Analyzed {results_count} results across {control_count} controls from {profile_count} profiles.')
print(f'{waiver_count} waivers created from {results_count_failed} failed controls in the given report.')
print(f'Waiver file {waiverfile} has been created.')
print(f'Thanks for using my waiverfy script!')

