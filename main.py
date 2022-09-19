# Licensed under GNU General Public License v3
import datetime
import json
import pathlib
import re
import textwrap
import threading
import logging
import winsound
import time
import os
from os.path import isfile, join


logging.basicConfig(format='%(asctime)s  %(message)s', level=logging.DEBUG)

### CONFIG

"""
Set friendly UUIDs here. These will have a different Beep here. 
Look up the Console to see the most recent UUIDs connected
"""
FRIENDLY_UUIDS = {
    "St4rF0x": 2039432,
    "WDX": 393577
}


BEEP_COOLDOWN_SECONDS = 5
HISTORY_FILE_TIMESTAMP_DELTA_SECONDS = 10
###

COMMANDER_HISTORY_DIR = join(os.getenv("LOCALAPPDATA"), "Frontier Developments", "Elite Dangerous", "CommanderHistory")
COMMANDER_TO_LAST_SEEN_LOOKUP: dict[int, int] = {}
LAST_MODIFIED_TIMESTAMP: int = 0
LAST_BEEP_TIMESTAMP: datetime.datetime = datetime.datetime.now()
CURRENT_VERSION: int = 1

def beep():
    winsound.Beep(500, 200)
    winsound.Beep(700, 200)
    pass


def beep_friendly():
    winsound.Beep(700, 200)
    winsound.Beep(500, 200)
    winsound.Beep(400, 200)
    pass


def check_for_updates():
    try:
        import urllib.request
        resp = urllib.request.urlopen("https://raw.githubusercontent.com/CMDR-WDX/elite-beepbeep/master/version")
        version_online = int(resp.read().decode("utf-8"))
        download_url = "https://github.com/CMDR-WDX/elite-beepbeep"
        if version_online > CURRENT_VERSION:
            # New Version available
            print(f"{'*' * 20}\n"
                  f"There is a new update available! Current local version is {CURRENT_VERSION}, available version is"
                  f" {version_online}.\nDownload at {download_url}\n{'*' * 20}")
        elif version_online == CURRENT_VERSION:
            print("This Version is Up to Date.")

    except Exception as err:
        print("Failed to check for an Update.")
        print(err)


def extract_commanders_from_history_file(abs_file_path: str) -> list[list[int]]:

    def create_commander_entry(json_entry: dict) -> list[int]:
        user_id = json_entry["CommanderID"]
        elite_epoch = json_entry["Epoch"]
        unix_epoch = convert_history_epoch_to_unix_epoch(elite_epoch)
        return [user_id, unix_epoch]

    with open(abs_file_path) as file:
        try:
            data = json.load(file)
            all_in_list = [a for a in data["Interactions"]]
            # Convert from weird Elite Epoch to Unix
            as_tuple = [create_commander_entry(a) for a in all_in_list if "Met" in a["Interactions"]]
            return as_tuple
        except Exception as err:
            print("Failed to read json file. Skipping")
            print(err)
            return []


def flatten(l):
    return [item for sublist in l for item in sublist]


def get_modified_files(first_run = False) -> list[str]:
    """
    This checks which Files have their "Last Modified"-Header is more recent than the last check
    """
    global LAST_MODIFIED_TIMESTAMP
    files_in_history_dir = [a for a in os.listdir(COMMANDER_HISTORY_DIR) if isfile(join(COMMANDER_HISTORY_DIR, a))]
    history_files = [a for a in files_in_history_dir if is_cmdr_history_file(a)]
    # Get History files whose timestamp is NEWER than the last check
    if first_run:
        commander_entries = \
            flatten([extract_commanders_from_history_file(join(COMMANDER_HISTORY_DIR, a)) for a in history_files])
        for [cmdr, timestamp] in commander_entries:
            COMMANDER_TO_LAST_SEEN_LOOKUP[cmdr] = timestamp

        LAST_MODIFIED_TIMESTAMP = int(datetime.datetime.now().timestamp())

    new_history_files = [a for a in history_files if
                         check_if_file_is_newer_than_timestamp(join(COMMANDER_HISTORY_DIR, a), LAST_MODIFIED_TIMESTAMP)]
    return new_history_files


def check_if_file_is_newer_than_timestamp(filepath: str, timestamp: int) -> bool:
    as_path = pathlib.Path(filepath)
    last_modified = int(as_path.stat().st_mtime)
    return last_modified > timestamp


def is_cmdr_history_file(name: str) -> bool:
    # Commander2482731.cmdrHistory
    regex = re.compile("^Commander\\d*\\.cmdrHistory$")
    temp = re.match(regex, name)
    return temp is not None


def convert_history_epoch_to_unix_epoch(history_epoch: int) -> int:
    return int((datetime.datetime(1601, 1, 1) + datetime.timedelta(seconds=history_epoch)).timestamp())


def print_commander_in_instance(c: int, friendly: bool):
    def get_friendly_name() -> str:
        keys = list(FRIENDLY_UUIDS.keys())
        vals = list(FRIENDLY_UUIDS.values())
        try:
            i = vals.index(c)
            return keys[i]
        except:
            return str(c)

    if friendly:
        cmdr_name = get_friendly_name()
        logging.info("CMDR {} came to steal your kills".format(cmdr_name))
    else:
        logging.info("CMDR w/ ID {} joined the instance".format(c))


def try_beep(is_beep_friendly: bool):
    now = datetime.datetime.now()
    global LAST_BEEP_TIMESTAMP
    delta = (now-LAST_BEEP_TIMESTAMP).total_seconds()
    if delta > BEEP_COOLDOWN_SECONDS:
        LAST_BEEP_TIMESTAMP = now
        if is_beep_friendly:
            beep_friendly()
        else:
            beep()


def aggregate_most_recent_commanders(new_cmdr_files: list[str]):
    new_commanders: list[int] = []

    new_cmdr_data: list[list[int]] = \
        flatten([extract_commanders_from_history_file(join(COMMANDER_HISTORY_DIR, e)) for e in new_cmdr_files])
    for [commander, timestamp] in new_cmdr_data:
        if commander not in COMMANDER_TO_LAST_SEEN_LOOKUP.keys():
            # Completely new Commander, not in List yet
            # Put that commander into the Repo
            COMMANDER_TO_LAST_SEEN_LOOKUP[commander] = timestamp
            new_commanders.append(commander)
        else:

            last_seen_dt = datetime.datetime.fromtimestamp(timestamp)
            in_repo_dt = datetime.datetime.fromtimestamp(COMMANDER_TO_LAST_SEEN_LOOKUP[commander])
            delta = (last_seen_dt-in_repo_dt).total_seconds()
            # More than 30 Seconds
            if delta > 30:
                COMMANDER_TO_LAST_SEEN_LOOKUP[commander] = timestamp
                new_commanders.append(commander)
    return new_commanders


check_for_updates()
# Initial Setup
get_modified_files(True)

logging.info("%d CMDRs in Cache. Ready and polling.", (len(COMMANDER_TO_LAST_SEEN_LOOKUP.keys())))
while True:
    time.sleep(1)
    logging.debug("\n\nStart new Poll")
    try:
        new_cmdr_history_files = get_modified_files()
        if len(new_cmdr_history_files) == 0:
            # There's no Update since the last beep.
            logging.debug("No newly modified Log file")
            continue
        most_recent_commanders: list[int] = aggregate_most_recent_commanders(new_cmdr_history_files)
        if len(most_recent_commanders) == 0:
            logging.debug("Logfile modified, but no new CMDR entries")
            continue
        only_friendly = True
        for commander in most_recent_commanders:
            is_friendly = commander in FRIENDLY_UUIDS.values()
            if not is_friendly:
                only_friendly = False
            print_commander_in_instance(commander, is_friendly)
        try_beep(only_friendly)
    except Exception as err:
        logging.exception("Whoops. Something broke in the main loop.")
        logging.exception(err, exc_info=True)
