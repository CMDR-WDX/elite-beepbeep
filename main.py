import datetime
import json
import pathlib
import re
import textwrap
import threading

import winsound
import time
import os
from os.path import isfile, join

COMMANDER_HISTORY_DIR = join(os.getenv("LOCALAPPDATA"), "Frontier Developments", "Elite Dangerous", "CommanderHistory")

### Config
"""
Set friendly UUIDs here. These will have a different Beep here. Look up the Console to see the most recent UUIDs connected
"""
FRIENDLY_UUIDS = [
    2039432,# Starf0x
    393577, # WDX
]

BEEP_COOLDOWN = 5
###

CURRENT_RELEVANT_HISTORY_FILE = None


def beep():
    winsound.Beep(500, 200)
    winsound.Beep(700, 200)
    pass


def beep_friendly():
    winsound.Beep(700, 200)
    winsound.Beep(500, 200)
    winsound.Beep(400, 200)
    pass


def check_for_most_recent_log_path():
    # Every Minute, in a separate Thread, this loop is invoked. It checks for a potentially new Netlog file
    global CURRENT_RELEVANT_HISTORY_FILE
    previous_loop_count_check = 0
    while True:
        all_files_in_netlog_dir = \
            [f for f in os.listdir(COMMANDER_HISTORY_DIR) if isfile(join(COMMANDER_HISTORY_DIR, f))]
        # Filter even further down by matching the pattern

        relevant_log_files: list[str] = []

        for entry in all_files_in_netlog_dir:
            if is_cmdr_history_file(entry):
                relevant_log_files.append(entry)
        if len(relevant_log_files) != previous_loop_count_check:
            # A new file was created
            most_recent_file = join(COMMANDER_HISTORY_DIR, get_most_recent_file(relevant_log_files))
            if CURRENT_RELEVANT_HISTORY_FILE != most_recent_file:
                print("[NEW HISTORY FILE] Tailing new History File at " + most_recent_file)
                CURRENT_RELEVANT_HISTORY_FILE = most_recent_file
        time.sleep(60)


def get_most_recent_file(all_file_names: list[str]):
    most_recent_file = ""
    most_recent_file_time = 0

    for entry in all_file_names:
        time_value = get_timestamp_from_file(entry)
        if time_value > most_recent_file_time:
            most_recent_file = entry
            most_recent_file_time = time_value
        elif time_value == most_recent_file_time:
            entry_suffix = int(entry.split(".")[2])
            most_recent_file_suffix = int(most_recent_file.split(".")[2])

            if entry_suffix > most_recent_file_suffix:
                most_recent_file = entry

    return most_recent_file


def get_timestamp_from_file(filename: str) -> int:
    full_path_str = join(COMMANDER_HISTORY_DIR, filename)
    last_modified = pathlib.Path(full_path_str).stat().st_mtime
    return int(last_modified)


def is_cmdr_history_file(name: str) -> bool:
    # Commander2482731.cmdrHistory
    regex = re.compile("^Commander\\d*\\.cmdrHistory$")
    temp = re.match(regex, name)
    return temp is not None


def convert_history_epoch_to_unix_epoch(history_epoch: int) -> int:
    return int((datetime.datetime(1601, 1, 1) + datetime.timedelta(seconds=history_epoch)).timestamp())


thread_check_dir = threading.Thread(target=check_for_most_recent_log_path, daemon=True, name="BeepBeep-DirChecker")
thread_check_dir.start()

###############################
# Wait for the most recent file to be found
while CURRENT_RELEVANT_HISTORY_FILE is None:
    time.sleep(1)

current_file_name: str = CURRENT_RELEVANT_HISTORY_FILE
currently_connected_cmdrs = []
last_beep_timestamp = int(datetime.datetime.utcnow().timestamp())

while True:
    time.sleep(1)
    if current_file_name != CURRENT_RELEVANT_HISTORY_FILE:
        current_file_name = CURRENT_RELEVANT_HISTORY_FILE
        print("[NEW HISTORY FILE] New history file loaded at ")
        print(current_file_name)
        print("")

    # Read the Entire file
    f = open(current_file_name)
    data = json.load(f)
    entries = []
    try:
        iterable = iter(data["Interactions"])
        for entry in iterable:
            commander_id = entry["UserID"]
            timestamp = entry["Epoch"]
            interactions = entry["Interactions"]
            if "Met" in interactions:
                entries.append([commander_id, convert_history_epoch_to_unix_epoch(timestamp)])
        entries.sort(key=lambda x: -x[1])
    except TypeError:
        print("Wrongly Structured JSON")

    if len(entries) > 0:
        # Get a list of all CMDRs with the most recent timestamp
        value = entries[0][1]
        relevant_entries = []
        for entry in entries:
            if entry[1] >= last_beep_timestamp:
                relevant_entries.append(entry)

        new_cmdrs = []

        for entry in relevant_entries:
            if entry[0] not in currently_connected_cmdrs:
                date_string = datetime.datetime.fromtimestamp(entry[1]).strftime("%Y-%m-%d @ %H:%M:%S")
                if entry[0] not in FRIENDLY_UUIDS:
                    print("New CMDR in History: "+str(entry[0]) + " - "+date_string + " IGT")
                else:
                    print("Friendly CMDR in History: "+str(entry[0]) + " - "+date_string + " IGT")
                new_cmdrs.append(entry)

        if len(new_cmdrs) > 0 and (value-last_beep_timestamp) > BEEP_COOLDOWN:
            last_beep_timestamp = value
            # If ANY of them is not a "friendly" marked, play default beep, else play friendly
            play_friendly = True
            for [name, _] in new_cmdrs:
                if name not in FRIENDLY_UUIDS:
                    play_friendly = False
                    break
            if play_friendly:
                beep_friendly()
            else:
                beep()
        # Push new "current" State
        currently_connected_cmdrs.clear()

        for [name, _] in relevant_entries:
            currently_connected_cmdrs.append(name)

    f.close()
