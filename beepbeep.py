# Licensed under GNU General Public License v3
from asyncio.log import logger
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
from dataclasses import dataclass

# You can change the logging level here. If stuff breaks, change set this to True to get more output
___DEBUG = True
if ___DEBUG:
    logging.basicConfig(format='%(asctime)s @ %(lineno)d  %(message)s', level=logging.DEBUG)
else:
    logging.basicConfig(format='%(asctime)s  %(message)s', level=logging.INFO)

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
###


@dataclass
class CommanderAndTimestamp:
    commander_id: int
    timestamp: datetime.datetime





class CommanderHistoryState:

    __listeners: list = []
    __last_cmdr_state: list[int] = []
    """
    Contains Callbacks that will be invoked when a new Commander was spotted
    """
 
    __most_recent_timestamp: datetime.datetime
   
   
    def subscribe_new_listener(self, cb):
        self.__listeners.append(cb)

    def get_init_debug_str(self, state: list[CommanderAndTimestamp]):
        output_lines = ["\t{}:{}\n".format(str(f.commander_id), str(f.timestamp)) for f in state]
        as_str = "".join(output_lines)
        return as_str

    def __init__(self, initial_state: list[CommanderAndTimestamp], name="None"):
        self.name = name
        logger.debug("Initializing new History State with the following initial state: \n%s", self.get_init_debug_str(initial_state))
        self._state = {}
        for entry in initial_state:
            self._state[entry.commander_id] = entry.timestamp
        self.__most_recent_timestamp = max(map(lambda x: x.timestamp, initial_state))


    def find_entry(self, commander_id) -> CommanderAndTimestamp | None:
        if commander_id in self._state.keys():
            return CommanderAndTimestamp(commander_id, self._state[commander_id])
        return None


    def _emit_events(self):
        data: list[CommanderAndTimestamp] = []
        keys = self._calculate_current_commander_ids()
        for key in keys:
            data.append(CommanderAndTimestamp(key, self._state[key]))
        for cb in self.__listeners:
            cb(data)

    def _calculate_current_commander_ids(self):
        """
        This Function should be run AFTER the current state has been updated
        It should return all CMDRs that are considered "active" now.
        """
        return_commanders: list[int] = []
        for key in self._state:
            timestamp = self._state[key]
            if timestamp >= self.__most_recent_timestamp:
                return_commanders.append(key)
        return return_commanders

    def push_new_state(self, entries: list[CommanderAndTimestamp]):
        needs_emit = [self._update_entry(f) for f in entries]
        
        calculated_state = self._calculate_current_commander_ids()
        
        is_subset = True
        for entry in calculated_state:
            if entry not in self.__last_cmdr_state:
                is_subset = False
                break
        
        self.__last_cmdr_state.clear()
        for entry in calculated_state:
            self.__last_cmdr_state.append(entry)
        
        # Only Update if some Entries have been Updated AND
        # the "new" set is NOT a subset of the "old" set
        #   Think CMDR A, B, C -> CMDR A,B 
        #   The new Set is a subset and should not create a Beep
        if any(needs_emit) and not is_subset:
            self._emit_events()

    def _update_entry(self, entry: CommanderAndTimestamp) -> bool:
        """
        This function will return True if the time is newer than the currently stored time.
        If the CMDR is not known they will be inserted into the lookup and True is returned also.
        """
        is_timestamp_newer = entry.timestamp > self.__most_recent_timestamp

        if is_timestamp_newer:
            logger.debug("New Most Recent Timestamp: %s", entry.timestamp)
            self.__most_recent_timestamp = entry.timestamp

        is_entry_new = entry.commander_id not in self._state.keys()
        self._state[entry.commander_id] = entry.timestamp
        
        return is_timestamp_newer or is_entry_new

    def get_most_recent_timestamp(self):
        return self.__most_recent_timestamp
        




class BeepHandler: 
    # If you want to change the beeps, do it here :)
    def _beep(self):
        winsound.Beep(500, 200)
        winsound.Beep(700, 200)


    def _beep_friendly(self):
        winsound.Beep(700, 200)
        winsound.Beep(500, 200)
        winsound.Beep(400, 200)


    def __init__(self, cooldown_seconds: int, friendly_ids: list[int], history_state_handles: list[CommanderHistoryState]) -> None:
        self.last_beep = datetime.datetime.now()
        self._cooldown = cooldown_seconds
        self._friendly = friendly_ids
        for entry in history_state_handles:
            entry.subscribe_new_listener(lambda x: self._handle_event(x, entry.name))
        
    def _handle_event(self, data : list[CommanderAndTimestamp], name: str = "None"):
        now = datetime.datetime.now()
        delta = (now - self.last_beep).total_seconds()
        if delta > self._cooldown:
            self.last_beep = now
            do_friendly_beep = all([f.commander_id in self._friendly for f in data])
            if do_friendly_beep:
                logger.info("History: %s A friend of yours is trying to steal your ganks :)", name)
                self._beep_friendly()
            else:
                logger.info("History: %s New CMDR in Instance", name)
                self._beep()




COMMANDER_HISTORY_DIR = join(os.getenv("LOCALAPPDATA"), "Frontier Developments", "Elite Dangerous", "CommanderHistory")
COMMANDER_HISTORY_LOOKUP: dict[int, CommanderHistoryState] = {}
LAST_MODIFIED_TIMESTAMP: datetime.datetime
CURRENT_VERSION: int = 1


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


def extract_commanders_from_history_file(abs_file_path: str) -> list[CommanderAndTimestamp]:

    def create_commander_entry(json_entry: dict) -> CommanderAndTimestamp:
        user_id = json_entry["CommanderID"]
        elite_epoch = json_entry["Epoch"]
        unix_epoch = convert_history_epoch_to_unix_epoch(elite_epoch)
        return CommanderAndTimestamp(user_id, datetime.datetime.fromtimestamp(float(unix_epoch)))

    with open(abs_file_path, "r") as file:
        try:
            data = json.load(file)
            all_in_list = [a for a in data["Interactions"]]
            # Convert from weird Elite Epoch to Unix
            return [create_commander_entry(a) for a in all_in_list if "Met" in a["Interactions"]]
        except Exception as err:
            logging.error("Failed to read json file. Skipping")
            logging.error(err)
            return []


def get_history_id_from_relative_filename(name: str) -> int:
    left_path = name.split(".")[0]
    just_number = left_path.removeprefix("Commander")
    return int(just_number)

def get_modified_files(first_run = False) -> list[str]:
    """
    This checks which Files have their "Last Modified"-Header is more recent than the last check
    """
    global LAST_MODIFIED_TIMESTAMP
    files_in_history_dir = [a for a in os.listdir(COMMANDER_HISTORY_DIR) if isfile(join(COMMANDER_HISTORY_DIR, a))]
    history_files = [a for a in files_in_history_dir if is_cmdr_history_file(a)]
    # Get History files whose timestamp is NEWER than the last check
    if first_run:
        history_file_to_cmdrs_in_list_lookup = \
            [(get_history_id_from_relative_filename(a),extract_commanders_from_history_file(join(COMMANDER_HISTORY_DIR, a))) for a in history_files]
        for history_file_id, entries in history_file_to_cmdrs_in_list_lookup:
            new_state = CommanderHistoryState(entries, str(history_file_id))
            global COMMANDER_HISTORY_LOOKUP
            COMMANDER_HISTORY_LOOKUP[history_file_id] = new_state

        LAST_MODIFIED_TIMESTAMP = datetime.datetime.now()

    new_history_files = [a for a in history_files if
                         check_if_file_is_newer_than_timestamp(join(COMMANDER_HISTORY_DIR, a), LAST_MODIFIED_TIMESTAMP)]
    LAST_MODIFIED_TIMESTAMP = datetime.datetime.now()
    return new_history_files


def check_if_file_is_newer_than_timestamp(filepath: str, timestamp: datetime.datetime) -> bool:
    as_path = pathlib.Path(filepath)
    last_modified = datetime.datetime.fromtimestamp(as_path.stat().st_mtime)

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



def aggregate_most_recent_commanders(new_cmdr_files: list[str]) -> list[tuple[int, list[CommanderAndTimestamp]]]:
    
    return_entries: list[tuple[int, list[CommanderAndTimestamp]]] = []

    for entry in new_cmdr_files:
        history_id = get_history_id_from_relative_filename(entry)
        res = extract_commanders_from_history_file(join(COMMANDER_HISTORY_DIR, entry))

        history_file_timestamp = COMMANDER_HISTORY_LOOKUP[history_id].get_most_recent_timestamp()
        res_new = []
        for entry in res:
            delta = (entry.timestamp - history_file_timestamp).total_seconds()
            if delta > 0.0:
                res_new.append(entry)

        if len(res_new) > 0:
            return_entries.append((history_id, res_new))

    return return_entries


check_for_updates()
# Initial Setup
get_modified_files(True)
# Set up a Beeper. This will create the beautiful Win96-esque beep that will notify you of your next gank targets :)
beeper = BeepHandler(BEEP_COOLDOWN_SECONDS, FRIENDLY_UUIDS.values(), list(COMMANDER_HISTORY_LOOKUP.values()))

logging.info("Ready and polling. %s History files are being polled.", (len(COMMANDER_HISTORY_LOOKUP.keys())))
while True:
    time.sleep(1)
    logging.debug("\n\nStart new Poll")
    try:
        new_cmdr_history_files = get_modified_files()
        logger.debug("%d Logfiles modified.", len(new_cmdr_history_files))
        if len(new_cmdr_history_files) == 0:
            # There's no Update since the last beep.
            logging.debug("No newly modified Log file")
            continue
        most_recent_commanders = aggregate_most_recent_commanders(new_cmdr_history_files)
        if len(most_recent_commanders) == 0:
            logging.debug("Logfile modified, but no new CMDR entries")
            continue
        # Notify the History File Handlers about new states. They will then emit Events. 
        # The Beep-Handler is registered to all those events and will send out Beeps as needed
        for history_file_id, update_state in most_recent_commanders:
            COMMANDER_HISTORY_LOOKUP[history_file_id].push_new_state(update_state)

    except Exception as err:
        logging.exception("Whoops. Something broke in the main loop.")
        logging.exception(err, exc_info=True)
        raise err
