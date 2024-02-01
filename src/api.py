"""
Implement an API for: 
 - https://reiseauskunft.bahn.de/bin/bhftafel.exe/<Station>
 - https://reiseauskunft.bahn.de/bin/traininfo.exe/<Train>

rt=0 | rt=1  (in the url) -> 0 means no delay info; 1 is the opposite
rtMode=0 | rtMode=1
"""

import re
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup


class Station:
  """API for https://reiseauskunft.bahn.de/bin/bhftafel.exe/
  
  It doesn't matter if the name is an id or a station name.
  """

  def __init__(self, name, check_version=False):
    self.check_version = check_version
    self.bhftafel_version = None
    self.excess_stations = set()  # TODO: use that somewhere
    self.delayed_causes = set()  # TODO: use that somewhere
    self.name = name
    request_time_date = datetime.now()
    self.request_date = request_time_date.strftime("%d.%m.%y")
    self.request_time = request_time_date.strftime("%H:%M")
    self.init()

  def init(self):
    self.html_document = self.get_data()
    self.data_package = self.extract_relevant_data(self.html_document)
    return self.data_package

  def get_data(self):
    """Craft post-body and fetch data.

    TODO: also possible to get data with a get request. what is better?
    """
    payload = {
      "input": self.name,
      "date": self.request_date,
      "time": self.request_time,
      "boardType": "dep",   # dep or arr
      "GUIREQProduct_0": "on",  # ICE-Züge
      "GUIREQProduct_1": "on",  # Intercity- und Eurocityzüge
      "GUIREQProduct_2": "on",  # Interregio- und Schnellzüge
      "GUIREQProduct_3": "on",  # Nahverkehr und sonstige Züge
      "GUIREQProduct_4": "on",  # S-Bahn
      "GUIREQProduct_5": "on",  # Busse
      "GUIREQProduct_6": "on",  # Schiffe
      "GUIREQProduct_7": "on",  # U-Bahnen
      "GUIREQProduct_8": "on",  # Straßenbahnen
      "GUIREQProduct_9": "on",  # Anruf-Sammeltaxi
      "start": "Suchen"
    }

    url = "https://reiseauskunft.bahn.de/bin/bhftafel.exe/dn?ld=43106&protocol=https:&rt=1&"

    response = requests.post(url, data=payload)
    return response.text
  
  def extract_relevant_data(self, html_document):

    parsed_html = BeautifulSoup(html_document, "html.parser")
    # TODO: for speed look into lxml as a parser and using css-selectors

    if self.check_version:
      meta_page_info = "".join(parsed_html.find("script").stripped_strings)
      for line in meta_page_info:
        line = line.strip()
        if line.startswith("digitalData.page.pageInfo.version"):
          version = line.split("=")[-1].strip(' "')
      self.bhftafel_version = version

    # do we have to dates? i.e. do we have to account for the change 
    dates_text = "".join(parsed_html.find("div", id="sqResult").h2.strong.stripped_strings)
    dates = re.findall(r"\d{2}.\d{2}.\d{2}", dates_text)
    two_dates = len(dates) > 0

    # create a list of stations that are also present (but that I didn't ask for)
    other_stations_text = parsed_html.find("p", "lastParagraph").find_all("a")
    other_stations = ["".join(a.stripped_strings) for a in other_stations_text]
    self.excess_stations.update(other_stations)

    all_rows = parsed_html.find_all("tr", id=re.compile("^journeyRow_\d+"))
    planed_time_before = None
    data_packages = list()

    for row in reversed(all_rows):
      # do platform in the beginning because the row might not belong to the requested station #
      platform_number = None
      platform_text = row.find("td", "platform")
      if platform_text is not None:
        platform_number = platform_text.find("strong")
        platform_text = "".join(platform_text.stripped_strings)
        if platform_number is not None:
          platform_number = "".join(platform_number.stripped_strings)
          platform_text = platform_text.replace(platform_number, "")
        platform = platform_text.lstrip(" -")
        if platform and platform in other_stations:
          continue

      data_package = dict()
      data_package["platformNumber"] = platform_number

      planed_time = str(row.find("td", "time").string)
      if two_dates:
        planed_time = datetime.strptime(planed_time + " " + dates[-1], "%H:%M %d.%m.%y")
        if planed_time_before is not None:
          diff = planed_time_before - planed_time
          if diff.total_seconds() < 0:
            planed_time -= timedelta(days=1)
      else:
        planed_time = datetime.strptime(planed_time + " " + self.request_date, "%H:%M %d.%m.%y")
      
      planed_time_before = planed_time
      data_package["planedTime"] = planed_time

      transportation_type_pic_url = row.find("td", "train").a.img["src"]
      transportation_type = re.search("(?<=/)[a-z_]+(?=_\d+x\d+.[a-z]+$)", transportation_type_pic_url).group()

      data_package["transportationType"] = transportation_type

      train_name_field = row.find_all("td", "train")[-1]
      train_url = "https://reiseauskunft.bahn.de" + str(train_name_field.a["href"])

      data_package["trainUrl"] = train_url

      train_name = [re.compile(r"\s+").sub(" ", word) for word in train_name_field.stripped_strings]
      train_name = " ".join(train_name)
      data_package["trainName"] = train_name

      route = row.find("td", "route")
      endstation = "".join(route.span.a.stripped_strings)
      data_package["endstation"] = endstation

      # sometimes there is extra info (mostly in red) in the route-box
      extra_info = route.find("div")
      if extra_info is not None:
        extra_infos = list()
        while route.find("div"):
          extra_info = route.div.extract()
          extra_infos.append(extra_info)

      # TODO: what do I do with this information?
          
      partial_route_raw = " - ".join([all_stops.replace("\n", " ") for all_stops in route.stripped_strings][1:])
      partial_route_raw = [stop.lstrip("- ") for stop in re.split(r"(?<=\d{2}:\d{2})", partial_route_raw) if len(stop) != 0]
      partial_route_raw = [stop.split("  ") for stop in partial_route_raw]
      partial_route = list()
      current_station_datetime = planed_time
      for stop, time in partial_route_raw:
        hours, minutes = time.split(":")
        planed_time_at_station_x = current_station_datetime.replace(hour=int(hours), minute=int(minutes))
        if current_station_datetime > planed_time_at_station_x:
          planed_time_at_station_x += timedelta(days=1)
        current_station_datetime = planed_time_at_station_x
        partial_route.append([stop, planed_time_at_station_x])
        stop = stop.removesuffix(" (Halt entfällt)")
        self.excess_stations.update([stop])

      data_package["partialRoute"] = partial_route


      # delayedBy, delayedTime, delayedCause, canceled
      data_package["issues"] = dict()
      issues = row.find("td", "ris")
      issues_text = "".join(issues.stripped_strings)
      delayed_time = None
      delayed_by = None
      cause = None
      canceled = False
      if len(issues_text) != 0:
        delayed_time_match = re.search(r"\d{2}:\d{2}", issues_text)
        if delayed_time_match is not None:
          delayed_time_text = delayed_time_match.group()
          hours, minutes = delayed_time_text.split(":")
          delayed_time = planed_time.replace(hour=int(hours), minute=int(minutes))
          delayed_by = delayed_time - planed_time
          if delayed_by.total_seconds() < 0:
            delayed_time += timedelta(days=1)
            delayed_by = delayed_time - planed_time
          elif delayed_by.total_seconds() == 0:
            delayed_by = None
            delayed_time = None
          cause = issues_text.replace(delayed_time_text, "")
          cause = cause.strip(", ")
        else:
          cause = issues_text
        canceled_match = re.search(r"(Fahrt fällt aus|Halt entfällt)", cause)
        canceled = canceled_match is not None
        if cause != "":
          self.delayed_causes.update([cause])
        else:
          cause = None
      data_package["issues"]["delayedTime"] = delayed_time
      data_package["issues"]["delayedBy"] = delayed_by
      data_package["issues"]["cause"] = cause
      data_package["issues"]["canceled"] = canceled

      data_packages.append(data_package)
      
    return [i for i in reversed(data_packages)]
      

class Train:
  """API for https://reiseauskunft.bahn.de/bin/traininfo.exe/"""
  def __init__(self, url):
    self.url = url
    self.init()
  
  def init(self):
    self.data = self.get_data(self.url)
    self.data_package = self.extract_relevant_data(self.data)
    return self.data_package

  def get_data(self, url):
    url = re.sub(r"rt=0", "rt=1", url)
    url = re.sub(r"rtMode=0", "rtMode=1", url)
    response = requests.get(url)
    return response.text

  def extract_relevant_data(self, data):
    parsed_html = BeautifulSoup(data, "html.parser")

    data_package = dict()

    *company_raw, = parsed_html.find("div", "tqRemarks").stripped_strings
    for entry in company_raw:
      if re.match(r"^Betreiber:", entry):
        company = entry.removeprefix("Betreiber:").strip()
        break
      else:
        company = None

    data_package["company"] = company

    train_name_text = parsed_html.find("div", class_="tqResults").find_next("h1").string
    train_name = " ".join(train_name_text.split()[2:])

    data_package["trainName"] = train_name

    train_date_text = str(parsed_html.find("h3", class_="trainroute"))
    train_date = re.search(r"\d{1,2}.\d{1,2}.\d{1,2}", train_date_text).group()
    train_date = datetime.strptime(train_date, "%d.%m.%y")
    data_package["trainDate"] = train_date

    route_rows = parsed_html.find_all("div", class_=re.compile(r"tqRow trainrow_\d"))
    planed_current_date = train_date
    delayed_current_date = train_date
    data_package["route"] = dict()
    for index, row in enumerate(route_rows):
      data_package["route"][index] = dict()

      station = row.find("div", class_=re.compile("station")).find("a").string
      data_package["route"][index]["station"] = station

      # Planed and delayed arrival time.
      arrival = row.find("div", class_="arrival")

      arrival_time = None
      arrival_time_raw = [string_ for string_ in arrival.stripped_strings if re.search(r"\d{1,2}:\d{2}", string_)]
      if len(arrival_time_raw) > 0:
        arrival_time = arrival_time_raw[0].split(" ")[-1]
      if arrival_time:
        hours, minutes = arrival_time.split(":")
        arrival_time = planed_current_date.replace(hour=int(hours), minute=int(minutes))
        if arrival_time < planed_current_date:
          arrival_time += timedelta(days=1)
        planed_current_date = arrival_time

      data_package["route"][index]["planedArrTime"] = arrival_time

      delayed_arrival_time = None
      if len(arrival_time_raw) > 1:
        delayed_arrival_time = arrival_time_raw[-1]
      if delayed_arrival_time:
        hours, minutes = delayed_arrival_time.split(":")
        delayed_arrival_time = planed_current_date.replace(hour=int(hours), minute=int(minutes))
        if delayed_arrival_time < delayed_current_date:
          delayed_arrival_time += timedelta(days=1)
        delayed_current_date = delayed_arrival_time
      else:
        delayed_current_date = arrival_time if arrival_time is not None else delayed_current_date
      data_package["route"][index]["delayedArrTime"] = delayed_arrival_time

      # Planed and delayed departure time.
      departure = row.find("div", class_="departure")
      
      departure_time_raw = [string_ for string_ in departure.stripped_strings if re.search(r"\d{1,2}:\d{2}", string_)]
      departure_time = None
      if len(departure_time_raw) > 0:
        departure_time = departure_time_raw[0].split(" ")[-1]
      if departure_time:
        hours, minutes = departure_time.split(":")
        departure_time = planed_current_date.replace(hour=int(hours), minute=int(minutes))
        if departure_time < planed_current_date:
          departure_time += timedelta(days=1)
        planed_current_date = departure_time
      data_package["route"][index]["planedDepTime"] = departure_time

      delayed_departure_time = None
      if len(departure_time_raw) > 1:
        delayed_departure_time = departure_time_raw[-1]
      if delayed_departure_time:
        hours, minutes = delayed_departure_time.split(":")
        delayed_departure_time = delayed_current_date.replace(hour=int(hours), minute=int(minutes))
        if delayed_departure_time < delayed_current_date:
          delayed_departure_time += timedelta(days=1)
        delayed_current_date = delayed_departure_time
      else:
        delayed_current_date = departure_time if departure_time is not None else departure_time
      data_package["route"][index]["delayedDepTime"] = delayed_departure_time

      platform_raw = row.find("div", class_="platform")
      platform_raw = list(platform_raw.stripped_strings)
      platform = None
      if len(platform_raw) > 1 and re.search("\d+", platform_raw[-1]) is not None:
        platform = platform_raw[-1]

      data_package["route"][index]["platform"] = platform

      issues_raw = row.find("div", class_="ris")
      *issues, = issues_raw.stripped_strings
      data_package["route"][index]["issues"] = dict()
      data_package["route"][index]["issues"]["canceled"] = "Halt entfällt" in issues
      issues = [string_ for string_ in issues if string_ not in ["Aktuelles", "Halt entfällt"]]
      data_package["route"][index]["issues"]["cause"] = issues[0] if len(issues) > 0 else None

    # TODO: use excessStations here as well 

    return data_package



if __name__ == "__main__":
  print("everything's fine")  