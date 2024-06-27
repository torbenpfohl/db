"""
Build stations database.
-> works mostly autonomous, i.e. handles ratelimits - just runs. DatabaseBuilder(<mode>) starts it.
   Strg+c can end the run.

   #TODO beginning: you can only call with one mode. (maybe later add add_country_code as a flag and do this work in in a seperate thread or so.)
"""

import os
import string
import json
import html
import time
import random
import xml.etree.ElementTree as ET
import sqlite3

import requests
import reverse_geocode


class DatabaseBuilder:
  """Building a database of "Deutsche Bahn"-stations in Germany.

  more ...
  called from:
  - Can get called as a standalone to extend the stations-database.
  - Can get called from another module, that acts as a manager.
  Acts as:
  - Extend database without country_code
  - Adds country_code to entries in the database

  internally:
    Extend the database with stations.
  exports:
    check_country, get_country
  
  side-effects:
    changes in the stations/stations.db
    changes in database_builder/*
  """
  
  CURRENT_DIRECTORY = os.getcwd()
  SAVED_STATES_PATH = os.path.join(CURRENT_DIRECTORY, "database_builder", "")
  DATABASE_PATH = os.path.join(CURRENT_DIRECTORY, "stations", "")
  STATIONS_DB_FILEPATH = os.path.join(DATABASE_PATH, "stations.db")
  LAST_PARITAL_CITY = "last_partial_city.txt"
  LAST_STATION_ID = "last_station_id.txt"
  COUNTRY_CODES_FILE = "country_codes.json"

  MODE = None
  GEONAMES_REQUEST_COUNTER = 0
  STARTTIME = None
  ENDTIME = None

  def register_geolocation_service(self):
    """#TODO add more reverse geocode functions.

    A function that calls an api needs to have the following structure:
      online_reverse_geocode(self, lat: str, lng: str, country_codes: dict[str, str] = dict(), allow_user_input=False) -> str:
      - needs to handle ratelimits; don't be afraid to let the whole program sleep for an hour or so. 
      (#TODO if we have enough endpoints: change this, and remove the ratelimited-endpoint from the list for the needed time.)
    """
    # For more: https://wiki.openstreetmap.org/wiki/Nominatim#Alternatives_.2F_Third-party_providers
    self.GEOLOCATION_SERVICES = {"local": [self._get_country_code_reverse_geocode,
                                      ], 
                                      "online": [self._get_country_code_geonames,
                                            self._get_country_code_openstreetmap,
                                            ]}

  def __init__(self, mode, timelimit: int = 60*30):  # , add_country_code=False):
    """Call with a mode. (Optional: set a runtime limit in seconds.)

    mode: "city" | "id" | "addCountry"
    function-modes: 
     - static: call x-times and sleep for x seconds
     - dynamic: call until load limit (error) and than sleep x seconds.
     -> implement so that I can change that later.

    example call-structur:
      -> startup (loads the last value)
      -> extend_with_partial_city (called x-times)
      -> close (stores the last processed value)
      -> 
    """

    self.MODE = mode
    self.STARTTIME = time.time()
    self.ENDTIME = self.STARTTIME + timelimit
    self.sqlite_connection = sqlite3.connect(self.STATIONS_DB_FILEPATH)
    self.register_geolocation_service()
    # self.add_country_code = add_country_code

    self._monitor()
    match mode:
      case "city":
        # Works on an empty database.
        last_partial_city = self._startup(self.SAVED_STATES_PATH, self.LAST_PARITAL_CITY)
        last_partial_city = self._run(self._extend_with_partial_city, last_partial_city)
        self._close(self.SAVED_STATES_PATH, self.LAST_PARITAL_CITY, last_partial_city)
      case "id":
        # Fill the spaces between ids in the database.
        cursor = self.sqlite_connection.cursor()
        cursor.execute("select count(*) from stations")
        database_entries_count = cursor.fetchall()
        if database_entries_count[0][0] >= 2:
          last_station_id = self._startup(self.SAVED_STATES_PATH, self.LAST_STATION_ID)
          last_station_id = self._run(self._extend_with_last_station_id, last_station_id)
          self._close(self.SAVED_STATES_PATH, self.LAST_STATION_ID, last_station_id)
        else:
          print(f"Not enough database entries in {self.STATIONS_DB_FILEPATH}. Needs at least 2.")
        cursor.close()
      case "addCountry":
        # Fills the country code field.
        self.COUNTRY_CODES = self._load_country_codes()
        self._run(self._add_countries_to_database)
        self._store_country_codes(self.COUNTRY_CODES)
      case "moveAndCheck":
        self._check_station_name()
      case _:
        print("not a valid mode value: 'city' or 'id', or 'addCountry")
    self.sqlite_connection.close()
    self._monitor()
  
  def _run(self, func, last_partial_city_or_id: str = None):
    """Generice function-runner.

    It's hard to determine the number of calls with _extend_with_last_station_id(...).
    """
    while True:
      if time.time() > self.ENDTIME:
        print("Timelimit reached. Exiting.")
        return last_partial_city_or_id
      try:
        if last_partial_city_or_id is not None:
          last_partial_city_or_id = func(last_partial_city_or_id)
        else:
          func()  # calls _add_countries_to_database
      except KeyboardInterrupt:
        print("userexit: Strg + C pressed")
        return last_partial_city_or_id
      except:
        return last_partial_city_or_id

  def _startup(self, folderpath, filename):
    """Load last saved partial city name or last saved id."""
    if not os.path.isdir(folderpath):
      os.mkdir(folderpath)
    if filename not in os.listdir(self.SAVED_STATES_PATH):
      open(os.path.join(self.SAVED_STATES_PATH, filename), "a").close()
      last_partial_city_or_id = ""
    else:
      with open(os.path.join(self.SAVED_STATES_PATH, filename), "r") as file:
        content = file.read()
      last_line = content.rstrip("\n")
      if last_line == "":
        last_partial_city_or_id = ""
      else:
        last_partial_city_or_id = last_line
    return last_partial_city_or_id

  def _close(self, foldername, filename, last_partial_city_or_id):
    """Save last processed partial city or id."""
    with open(os.path.join(foldername, filename), "w", encoding="utf-8") as file:
      file.write(last_partial_city_or_id)
    return None
  
  def _store_stations(self, stations):
    """Add stations that are not in the database to it."""
    cursor = self.sqlite_connection.cursor()
    if len(stations) > 0:
      columns = ",".join(stations[0].keys())
      columnCount = len(stations[0].keys())
      cursor.execute(f"CREATE TABLE if not exists stations({columns})")
      result = cursor.execute("SELECT stationId FROM stations")
      present_station_ids = result.fetchall()
      present_station_ids = [id[0] for id in present_station_ids]
      stations_for_database = list()
      for station in stations:
        if station["stationId"] not in present_station_ids:
          stations_for_database.append(tuple(station.values()))
      print(stations_for_database)  # TODO: test
      if len(stations_for_database) > 0:
        placeholders = ",".join(["?"] * columnCount)
        cursor.executemany(f"INSERT INTO stations VALUES({placeholders})", stations_for_database)
        self.sqlite_connection.commit()
      cursor.close()
    return None
  
  def _extend_with_partial_city(self, last_partial_city):
    """Get station suggestions, stores them and returns the last processed partial city."""
    next_partial_city = self._next_partial_city(last_partial_city)
    stations = self._get_stations(next_partial_city)
    # if self.add_country_code:
    #   for station in stations:
    #     country_code = self.get_country_code(station)
    #     if country_code is not None:
    #       station["country"] = country_code
    if len(stations) > 0:
      self._store_stations(stations)  
    return next_partial_city

  #@register_post_processing
  def _extend_with_last_station_id(self, last_station_id):
    """Based on the database of station ids, it adds -1 and +1 to the id to find new stations.
    
    Based on the last processed station (stored in a file),
      the function gets the following station from the database.
      With station id it calles forwards and backwards to find new
      stations.
    
    Requires that a minimum of two stations are stored in the database.
    """
    stations = list()
    cursor = self.sqlite_connection.cursor()
    request = cursor.execute(f"select stationId from stations where stationId > '{last_station_id}' order by stationId asc")
    station_id = request.fetchone()[0]
    station_id_upper_limit = request.fetchone()[0]

    backwards_found_stations = self._backwards(station_id, last_station_id)
    stations.extend(backwards_found_stations)

    forwards_found_stations, last_station_id = self._forwards(station_id, station_id_upper_limit)
    stations.extend(forwards_found_stations)

    cursor.close()
    if len(stations) > 0:
      self._store_stations(stations)
    return last_station_id

  #@register_post_processing
  def _add_countries_to_database(self):
    """Add the right country to the database entries.

    Defines a box (min and max values for lat and lng) 
      and all the others, that are not in there,
      are passed to a function to get the right country code.
    """
    # big box
    # - lat 48-54 lng: 8.5-12
    # regional boxes:
    # - lat: 51-54 lng: 12-14
    # - lat: 49.5-52 lng: 7-8.5
    # - lat: 50-51.5 lng: 6.5-7
    # - lat: 48-49.5 lng: 12-12.5
    # - lat: 54-54.5 lng: 8.5-11.5
    bounds = [
      {"latLower": 48, "latUpper": 54, "lngLower": 8.5, "lngUpper": 12},
      {"latLower": 51, "latUpper": 54, "lngLower": 12, "lngUpper": 14},
      {"latLower": 49.5, "latUpper": 52, "lngLower": 7, "lngUpper": 8.5},
      {"latLower": 50, "latUpper": 51.5, "lngLower": 6.5, "lngUpper": 7},
      {"latLower": 48, "latUpper": 49.5, "lngLower": 12, "lngUpper": 12.5},
      {"latLower": 54, "latUpper": 54.5, "lngLower": 8.5, "lngUpper": 11.5},
    ]
    cursor_empty_country_codes = self.sqlite_connection.cursor()
    cursor_update_country_code = self.sqlite_connection.cursor()
    request_empty_country_codes = cursor_empty_country_codes.execute("select * from stations where country is NULL order by stationId")
    station_name, station_id, lat, lng, country = request_empty_country_codes.fetchone()
    for bound in bounds:
      if bound["latLower"] <= float(lat) <= bound["latUpper"] and \
          bound["lngLower"] <= float(lng) <= bound["lngUpper"]:
        cursor_update_country_code.execute(f"update stations set country='DE' where stationId='{station_id}'")
        self.sqlite_connection.commit()
        break
    else:
      country_code = self.get_country_code(lat=lat, lng=lng)
      if country_code != None:
        cursor_update_country_code.execute(f"update stations set country='{country_code}' where stationId='{station_id}'")
        self.sqlite_connection.commit()
    return None

  #@register_post_processing
  def _extend_with_overlooked_ids(self):
    """
    search for stationId-ranges that are not in the database yet
    e.g. 000102569 to 000102587, because e.g. 000102573 is a valid stationId
    """
    pass  #TODO

  #@register_post_processing
  def _check_station_name(self):
    """Check the station name in the stations.db database. #Report
    
    Because e.g. 8000105 (Frankfurt(Main)Hbf) has a wrong name. In that run the latitude/longitude values are fixed as well.
    """
    _stations_db_filepath = os.path.join(self.DATABASE_PATH, "stations_reported.db")
    connection = sqlite3.connect(_stations_db_filepath)
    cursor = connection.cursor()
    cursor_old_database = self.sqlite_connection.cursor()
    cursor_old_database.execute("select * from stations")
    all_entries_old_database = cursor_old_database.fetchall()
    cursor_old_database.close()
    all_entry_ids_old_database = [entry[1] for entry in all_entries_old_database]
    cursor_new_database = connection.cursor()
    try:
      cursor_new_database.execute("select * from stations")
      all_entries = cursor_new_database.fetchall()
      all_entry_ids = [entry[1] for entry in all_entries]
      all_unique_entry_ids_old_database = set(all_entry_ids_old_database)
      all_unique_entry_ids = set(all_entry_ids)
      entries_todo = all_unique_entry_ids_old_database.difference(all_unique_entry_ids)
      entries_todo = list(entries_todo)
    except:
      entries_todo = all_entry_ids_old_database
    cursor_new_database.close()
    print("todos: ", len(entries_todo))
    need_to_run_create_table = True
    for station_id in entries_todo:
      station = self._get_stations(station_id)
      print(station)
      if len(station) == 1:
        columns = ",".join(station[0].keys())
        columnCount = len(station[0].keys())
        if need_to_run_create_table:
          cursor.execute(f"CREATE TABLE if not exists stations({columns})")
          need_to_run_create_table = False
        placeholders = ",".join(["?"] * columnCount)
        cursor.execute(f"INSERT INTO stations VALUES({placeholders})", tuple(station[0].values()))
        connection.commit()
      else:
        print("this should not be printed! ", station_id, station)
    cursor.close()
    connection.close()
    return None


  def _load_country_codes(self) -> dict[str, str]:
    """Load country codes, i.e. "DE": "DE", "Deutschland": "DE", etc. and return them as a dict.

    Uses ISO 3166-1 alpha-2 codes.
    """
    if not os.path.isdir(self.SAVED_STATES_PATH):
      os.mkdir(self.SAVED_STATES_PATH)
    if self.COUNTRY_CODES_FILE not in os.listdir(self.SAVED_STATES_PATH):
      country_codes = dict()
      with open(os.path.join(self.SAVED_STATES_PATH, self.COUNTRY_CODES_FILE), "a") as file:
        json.dump(country_codes, file)
    else: 
      with open(os.path.join(self.SAVED_STATES_PATH, self.COUNTRY_CODES_FILE), "r") as file:
        country_codes = json.load(file)
    return country_codes

  def _store_country_codes(self, country_codes):
    """Save the country codes to a file."""
    if not os.path.isdir(self.SAVED_STATES_PATH):
      os.mkdir(self.SAVED_STATES_PATH)
    with open(os.path.join(self.SAVED_STATES_PATH, self.COUNTRY_CODES_FILE), "w") as file:
      json.dump(country_codes, file)
    return None

  def _backwards(self, station_id: str, station_id_lower_limit: str) -> list[dict]:
    """Go backwards from a station_id starting point and return a list of stations.
    
    Stop when a last_station_id-bottom is reached 
      OR the "Deutsche Bahn"-API does not recognize 
      the station_id as a valid station.
    """
    new_stations = list()
    station_id = str(int(station_id) - 1).rjust(9, "0")
    while station_id_lower_limit < station_id:
      stations = self._get_stations(station_id)
      if len(stations) == 1:
        new_stations.extend(stations)
      else:
        break
      station_id = str(int(station_id) - 1).rjust(9, "0")
    return new_stations

  def _forwards(self, station_id: str, station_id_upper_limit: str) -> tuple[list[dict], str]:
    """Go forward from station_id and return a list of stations and the last valid station id.
    
    Stop when the next_station_id_in_database is reached
      OR the "Deutsche Bahn"-API does not recognize 
      the station_id as a valid station.
    """
    new_stations = list()
    last_valid_station_id = station_id
    while True:
      station_id = str(int(station_id) + 1).rjust(9,"0")
      if station_id == station_id_upper_limit:
        last_valid_station_id = station_id
        break
      stations = self._get_stations(station_id)
      if len(stations) == 1:
        new_stations.extend(stations)
        last_valid_station_id = station_id
      else:
        break
    return new_stations, last_valid_station_id

  @staticmethod
  def _next_partial_city(last_partial_city: str) -> str:
    """Determine next letter-sequence used as input for bahn-api."""
    # TODO: write a test for this function
    letters = string.ascii_lowercase + " _"
    if last_partial_city == "":
      return letters[0]
    next_partial_city = ""
    flag = 0
    last_partial_city_reversed = "".join([i for i in reversed(last_partial_city)])
    for index, letter in enumerate(last_partial_city_reversed):
      if letter == letters[-1]:
        next_partial_city += letters[0]
        flag = 1
      else:
        next_partial_city += letters[letters.find(letter) + 1] + last_partial_city_reversed[index+1:]
        flag = 0
        break
    if flag == 1:
      next_partial_city = letters[0] + next_partial_city
    next_partial_city = "".join([i for i in reversed(next_partial_city)])
    return next_partial_city

  @staticmethod
  def _get_stations(partial_city_or_station_id: str) -> list[dict]:
    """Fetches "Deutsche Bahn" json-data and extracts relevant data."""
    sleeptime = random.randint(0, 21)
    time.sleep(sleeptime / 7)
    url = f"https://reiseauskunft.bahn.de/bin/ajax-getstop.exe/dn?REQ0JourneyStopsS0A=1&REQ0JourneyStopsF=excludeMetaStations&REQ0JourneyStopsS0G={partial_city_or_station_id}&js=true"
    try:
      response = requests.get(url)
      data = response.text
      if data.startswith("SLs.sls="):
        data = data.removeprefix("SLs.sls=")
      if data.endswith(";SLs.showSuggestion();"):
        data = data.removesuffix(";SLs.showSuggestion();")
      data = json.loads(data)

      stations = data["suggestions"]
      stations_formated = list()
      for station in stations:
        try:  # e.g. mode == "id"
          request_id = int(partial_city_or_station_id)
          if int(station["extId"]) != request_id:  # e.g. "Km. 109+000 H." (005327747) turns up for other ids as well (000112463, 000112464, ...) 
            continue
        except:
          pass
        station_name = html.unescape(station["value"])
        station_id = station["extId"]
        coded_id = station["id"]

        lat = station["ycoord"]
        if lat.startswith("-") and len(lat) < 7:
          lat = "-" + lat.lstrip("-").rjust(6, "0")
        elif len(lat) < 6:
          lat = lat.rjust(6, "0")
        if lat[:-6] == "":
          lat = "0" + "." + lat[-6:]
        elif lat[:-6] == "-":
          lat = "-" + "0" + "." + lat[-6:]
        else:
          lat = lat[:-6] + "." + lat[-6:]

        lng = station["xcoord"]
        if lng.startswith("-") and len(lng) < 7:
          lng = "-" + lng.lstrip("-").rjust(6, "0")
        elif len(lng) < 6:
          lng = lng.rjust(6, "0")
        if lng[:-6] == "":
          lng = "0" + "." + lng[-6:]
        elif lng[:-6] == "-":
          lng = "-" + "0" + "." + lng[-6:]
        else:
          lng = lng[:-6] + "." + lng[-6:]

        station_formated = {"stationName": station_name,
                            "stationId"  : station_id,
                            "lat"        : lat,
                            "lng"        : lng,
                            "country"    : None
                            }
        stations_formated.append(station_formated)
      return stations_formated
    except:
      print("Problem with the deutsche bahn api.")
      return []
  
  
  #@register_geolocation_service(location="online")
  def _get_country_code_geonames(self, lat: str, lng: str, country_codes: dict[str, str] = dict(), allow_user_input=False) -> str:
    """Call geonames.org with lat and lng and return a geocode.

    hourly limit of 1000 'credits' per ip; one request to that endpoint seems to take 3 credits => max. 333 requests / hour
    """
    url = f"https://www.geonames.org/findNearbyPlaceName?lat={lat}&lng={lng}"
    if self.GEONAMES_REQUEST_COUNTER >= 333:
      try:
        response = requests.get(url)
        self.GEONAMES_REQUEST_COUNTER += 1
        # TODO: test the response in case of a rate limit blocking; different status_code?
        root = ET.fromstring(response.text)
        country = root[0].find("countryCode").text
        alpha_2_code = country_codes.get(country)
        if alpha_2_code:
          return alpha_2_code
        elif allow_user_input:
          alpha_2_code = self._ask_user_for_alpha_2_code(country)
          country_codes[country] = alpha_2_code
          return alpha_2_code, country_codes
        else:
          return None
      except:
        print("# Ratelimit (counter > 333) for geonames-api reached. Sleep for an hour.")
        time.sleep(60*60)
        return None
    else:
      print("# Ratelimit for geonames-api reached. Sleep for an hour.")
      time.sleep(60*60)
      return None

  #@register_geolocation_service(location="online")
  def _get_country_code_openstreetmap(self, lat: str, lng: str, country_codes: dict[str, str] = dict(), allow_user_input=False) -> str:
    """Call openstreetmap.org with lat and lng and return a geocode.
    
    https://nominatim.org/release-docs/develop/api/Search/
    Max. 1 requests / second; add a http-referer/user-agent.
    """
    # Try not to overload the api.
    sleeptime = random.randint(2,4)
    time.sleep(sleeptime)
    headers = {"user-agent": "bahn_station_classifier/0.1.0"}
    url = f"https://nominatim.openstreetmap.org/search?q={lat}+{lng}&format=geocodejson"
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
      response = response.json()
      if len(response) == 0:
        return None
      address_name = response["features"]["properties"]["geocoding"]["label"]
      country = address_name.split(",")[-1].strip()
      alpha_2_code = country_codes.get(country)
      if alpha_2_code:
        return alpha_2_code
      elif allow_user_input:
        alpha_2_code = self._ask_user_for_alpha_2_code(country)
        country_codes[country] = alpha_2_code
        return alpha_2_code, country_codes
      else:
        return None
    else:
      print("openstreetmap-api returned an error. Need to analyse that! Sleep for an hour - just in case.")
      time.sleep(60*60)
      return None

  #@register_geolocation_service(location="local")
  def _get_country_code_reverse_geocode(self, lat: str, lng: str) -> str:
    """Check geolocations with local package reverse_geocode.
    
    Unreliable especially in border regions.
    """
    address = reverse_geocode.search([(float(lat), float(lng))])
    country_code = address[0]["country_code"]
    return country_code

  def _ask_user_for_alpha_2_code(self, country: str) -> str:
    while True:
      alpha_2_code = input(f"enter ISO 3166-1 alpha-2 code for '{country}': ")
      if len(alpha_2_code) >= 2:
        return alpha_2_code
      print("Please enter a valid alpha 2 code.")

  def get_country_code(self, station=None, *, lat=None, lng=None, allow_user_input=False) -> str:
    """Gets the country code of station and returns it.

    Call local geocode-package and one online service.
    If they are not the same:
      -> Call another service until you two services get the same country code.

    return None, if something went wrong 
      (e.g. rate limit, not able to identify the country)
    """
    online_services = self.GEOLOCATION_SERVICES["online"].copy()
    local_services = self.GEOLOCATION_SERVICES["local"].copy()
    if station is not None:
      lat = station["lat"]
      lng = station["lng"]
    
    countries = list()
    country_code = None
    while True:
      if len(countries) >= 2:
        unique_countries = list(set(countries))
        if len(unique_countries) != len(countries):
          countries_and_occurrence = sorted([(u, countries.count(u)) for u in unique_countries], key=lambda x: x[-1], reverse=True)
          country_code = countries_and_occurrence[0][0]
          print("COUNTRY CODE: ", country_code, "- choosen from list:", countries)  #TODO: test, remove
          break
      if len(online_services) == 0 and len(local_services) == 0:
        break
      if len(online_services) > 0:
        online_service = random.choice(online_services)
        online_services.remove(online_service)
        if allow_user_input:
          online_result, self.COUNTRY_CODES = online_service(lat, lng, self.COUNTRY_CODES, allow_user_input=allow_user_input)
        else:  
          online_result = online_service(lat, lng, self.COUNTRY_CODES, allow_user_input=allow_user_input)
        if online_result is not None:
          countries.append(online_result)
      if len(local_services) > 0:
        local_service = random.choice(local_services)
        local_services.remove(local_service)
        local_result = local_service(lat, lng)
        if online_result is not None:
          countries.append(local_result)

    return country_code

  def check_country(self, station, country_code=None):
    """Checks if the station is in country_code and returns boolean.
    
    If user input is not allowed (default) result might be wrong.
    """
    if country_code is None:
      country_code = station["country"]
    return country_code == self.get_country_code(station)

  def _monitor(self):
    """Show some database- and state-information."""
    with open(os.path.join(self.SAVED_STATES_PATH, self.LAST_PARITAL_CITY)) as file:
      print(file.read().strip())
    with open(os.path.join(self.SAVED_STATES_PATH, self.LAST_STATION_ID)) as file:
      print(file.read().strip())
    connection = sqlite3.connect(self.STATIONS_DB_FILEPATH)
    cursor = connection.cursor()
    cursor.execute("select count(*) from stations")
    result = cursor.fetchall()
    print("Number of stations in database: ", result)
    cursor.execute("select count(*) from stations where country is not NULL")
    result = cursor.fetchall()
    print("Number of stations with country code: ", result)
    connection.close()






class Analyse:
  def __init__(self, partialCity):
    data = self.get(partialCity)
    self.work(data)

  def get(self, partialCity):
    # partialCity = "darmst_"
    url = f"https://reiseauskunft.bahn.de/bin/ajax-getstop.exe/dn?REQ0JourneyStopsS0A=1&REQ0JourneyStopsF=excludeMetaStations&REQ0JourneyStopsS0G={partialCity}&js=true"
    response = requests.get(url)
    data = response.text
    if data.startswith("SLs.sls="):
      data = data.removeprefix("SLs.sls=")
    if data.endswith(";SLs.showSuggestion();"):
      data = data.removesuffix(";SLs.showSuggestion();")
    jData = json.loads(data)
    return jData

  def work(self, data):
    lData = data["suggestions"]
    namesAndIds = list()
    for row in lData:
      stationName = row["value"]
      stationId = row["extId"]
      namesAndIds.append([stationName, stationId])
    for station in namesAndIds:
      print(station)


if __name__ == "__main__":
  # for abc in string.ascii_lowercase:
    # analyse = Analyse(abc)
  DatabaseBuilder("moveAndCheck")
  # DatabaseBuilder.loadCountryCodes()