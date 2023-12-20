"""
vl einmal am tag.
  getting or accessing an up-to-date list of stations

hauptaufgabe.
 die daten von der station holen
  a. aufbereiten und abspeichern (inkl. abfragezeit speichern)
  b. festlegen, wann die nächste anfrage stattfinden soll

extra. 
  stichprobenartig testen, ob die abstände zwischen den abfragen ok sind
"""

from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
import re
import sqlite3
import os

class Station:
  """
  the 'name' of the station is automaticly inserted from the database of
  stations, it actually doesn't matter if the name is the stationId or
  the stationName
  storeData uses the stationId as the table-name in the database
  """
  dbPath = os.getcwd()+os.sep+"stations"+os.sep+"information.db"

  def __init__(self, name):
    self.excessStations = set()
    self.name = name
    requestTimeDate = datetime.now()
    self.requestDate = requestTimeDate.strftime("%d.%m.%y")
    self.requestTime = requestTimeDate.strftime("%H:%M")
    #self.requestDate = "03.09.23"  #test
    #self.requestTime = "23:44"     #test
    self.htmlDocument = self.getData()
    self.dataPackage = self.extractRelevantData(self.htmlDocument)
    print(self.dataPackage, requestTimeDate)
    print(len(self.dataPackage))
    try:
      stationId = int(self.name)
      #self.storeData(self.dataPackage, requestTimeDate, self.name)
    except:
      pass
    print(self.excessStations)
    #return self.excessStations


  def getData(self):
    """
    also possible to get data with a get request
    what is better?
    """
    payload = {
      "input": self.name,
      "date": self.requestDate,
      "time": self.requestTime,
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
  
  def extractRelevantData(self, htmlDocument):
    # digitalData.page.pageInfo.version = "5.45.DB.R23.08.1.a (customer/hcudb/release/23.08.1.a.0) [Aug  5 2023]"
    # --> i.e. tracking changes to the layout!

    parsedHtml = BeautifulSoup(htmlDocument, "html.parser")
    # for speed look into lxml as a parser and using css-selectors

    # id = journeyRow_1, journeyRow_2, ...
    #   class = time        # reguläre abfahrtszeit
    #   class = train       # NV, ICE, etc. ("codiert" in bild) + a-href zum zugplan
    #   class = train       # a-href zum zugplan -> dann zugname/-nummer
    #   class = route       # zielhalt + href zur dortigen zugtafel + simpler zugplan
    #   class = platform    # bahnsteig
    #   class = ris         # besonderheiten: zugausfall, verspätung, z.T. auch meldung von pünktlichkeit

    # do we have to dates? 
    datesText = "".join([word for word in parsedHtml.find("div", id="sqResult").h2.strong.stripped_strings])
    dates = re.findall(r"\d{2}.\d{2}.\d{2}", datesText)
    if dates:
      rowDate = 2
    # wenn dates einen Wert hat (zwei-Elemente-Liste), dann muss ich 
    # 1. schauen, ob es ein aufeinanderfolgendes datum ist
    # 1.a. yes -> 2.
    # 1.b. no  -> no idea...
    # 2. schauen, ob ein tageswechsel statt findet, d.h. ob die zeit irgendwo von
    #    23:xx auf 00:xx umspringt.
    ## IDEE 1:
    # 1. alle zeiten werden auf dem "höchsten" datum initalisiert
    # 2. dann gehe ich von der letzten Reihe rückwärts durch die Liste und 
    #    prüfe, ob die vorherige Zeit (Uhrzeit inkl. Datum) kleiner ist, als
    #    die derzeitige.
    #    wenn ja, dann bleibt das datum so
    #    wenn nein, dann wird das datum für die vorherigen Einträge um 
    #    einen Tag reduziert und es geht weiter
    else:
      rowDate = 1

    print(dates)

    # create a list of stations that are also present (but that I didn't ask for)
    otherStationsText = parsedHtml.find("p", "lastParagraph").find_all("a")
    otherStations = ["".join(a.stripped_strings) for a in otherStationsText]
    self.excessStations.update(otherStations)
    print(otherStations)

    allRows = parsedHtml.find_all("tr", id=re.compile("^journeyRow_\d+"))

    print("Rows in document:", len(allRows))

    # reverse through allRows because this way I can validate the planedTime
    #   and therefore calculate the delayedTime here too 
    planedTimeBefore = None
    dataPackages = list()
    for row in reversed(allRows):
      # do platform in the beginning because the row might not belong to the
      # requested station 
      platform = "".join(row.find("td", "platform").stripped_strings)
      platform = platform[1:] if platform.startswith("-") else platform
      platformNumber = re.search(r"^\d*", platform).group()
      if platformNumber:
        platform = platform.replace(platformNumber, "")
      if platform and platform in otherStations:
        continue
      dataPackage = dict()  # where all information gets stored
      dataPackage["platformNumber"] = platformNumber

      planedTime = str(row.find("td", "time").string)
      # transform planedTime to datetime-object
      # also: make sure the date is right
      if rowDate == 2:
        planedTime = datetime.strptime(planedTime+" "+dates[-1], "%H:%M %d.%m.%y")
        if planedTimeBefore:
          diff = planedTimeBefore - planedTime
          if diff.total_seconds() < 0:
            planedTime -= timedelta(days=1)
      else:
        planedTime = datetime.strptime(planedTime+" "+self.requestDate, "%H:%M %d.%m.%y")
      planedTimeBefore = planedTime
      dataPackage["planedTime"] = planedTime

      transportationTypePicUrl = row.find("td", "train").a.img["src"]
      transportationType = re.search("(?<=/)[a-z_]+(?=_\d+x\d+.[a-z]+$)", transportationTypePicUrl).group()
      dataPackage["transportationType"] = transportationType

      trainNameField = row.find_all("td", "train")[-1]
      trainUrl = "https://reiseauskunft.bahn.de" + str(trainNameField.a["href"])
      dataPackage["trainUrl"] = trainUrl
      # TODO: how long is the url valid?

      trainName = [re.compile(r"\s+").sub(" ", word) for word in trainNameField.stripped_strings]
      trainName = " ".join(trainName)
      dataPackage["trainName"] = trainName

      route = row.find("td", "route")
      endstation = str("".join([word for word in route.span.a.stripped_strings]))
      dataPackage["endstation"] = endstation

      # extract route info in list of 2-tuples (station, planedTimeOnStation)
      # do i need the time? if yes: than i need to verify which day and all that..
      # 
      if route.img:
        route.img.replace_with("-")
      route = "".join(route.stripped_strings).removeprefix(endstation).replace("\n", " ").split(" - ")
      # route = [tuple(s.split("  ")) for s in route]
      route = [placeAndTime.split("  ")[0].replace(" (Halt entfällt)", "") for placeAndTime in route]
      self.excessStations.update(route)
      # do I make an extra call to the train-url and get the stations (and also 
      # add them to the train)
      # do I need a database for the trains?

    # TODO: combine delayed stuff into 'issues and add a field for 'Fahrt fällt aus' with boolean datatype
      issues = row.find("td", "ris")
      issuesText = "".join([word for word in issues.stripped_strings])  # "".join(issues.stripped_strings)
      delayedTime = None
      delayedBy = None
      delayCause = None
      if len(issuesText) != 0:
        # TODO: also search for a new time, like a new date (if present)
        #   as well as understanding, what other configurations are possible in this cell
        # TODO: look in the route-box for red text - it might contain more reasons for delays 
        delayedTimeMatch = re.search(r"\d{2}:\d{2}", issuesText)
        if delayedTimeMatch:
          delayedTime = delayedTimeMatch.group()
          delayCause = issuesText.replace(delayedTime, "")
          if delayCause == "":
            delayCause = None
          # delayed by
          #   if date is not available with the issuesText, than it will be
          #   obvious while calculation the delayed by value (because it will
          #   be negative)
          hours, minutes = delayedTime.split(":")
          delayedTime = planedTime.replace(hour=int(hours), minute=int(minutes))
          delayedBy = delayedTime - planedTime
          if delayedBy.total_seconds() == 0:
            delayedTime = None
            delayedBy = None
          elif delayedBy.total_seconds() < 0:
            delayedTime += timedelta(days=1)
            delayedBy += timedelta(days=1)
        else:
          delayCause = issuesText
      dataPackage["delayedTime"] = delayedTime
      dataPackage["delayedBy"] = delayedBy
      dataPackage["delayCause"] = delayCause

      delayOnTime_dbClass = "delayOnTime" in issues.span["class"] if issues.span else None
      dataPackage["delayOnTime"] = delayOnTime_dbClass

      dataPackages.append(dataPackage)
    return [i for i in reversed(dataPackages)]
  
  # determine next call-/query-time
  
  def storeData(self, dataPackage, requestTimeDate, stationId):
    # metadaten speichern (abfragezeit, ?)
    # eine große tabelle oder viele Kleine (z.B. für jede station eine, 
    # oder für jeden zug eine)
    # beispielabfragen: 
    # - kumulierte verspätungen an allen bahnhöfen über eine bestimmte zeit
    # - verspätungen an einem bahnhof über bestimmte zeit
    # - verspätungsverlauf eines bestimmten zuges, auf einer bestimmten strecke
    # - auflistung von verspätungsgründen (welche und wie viele jeweils)
    # - bei wie vielen verspätungen gründe angegeben sind
    # - wie viele züge fahren an einem bahnhof durchschnittlich
    # ziel:
    # - aufzeichnung aller verbindungen
    # - aufzeichnung aller verspätungen (verlauf?, ultimative) 
    # wir erstellen tabellen für:
    # -> die stationen (jede station eine)
    # -> für züge (zugname gepaart mit einem spezifischen tag und abfahrt- und 
    #    ankunftbahnhof)
    con = sqlite3.connect(self.dbPath)
    cur = con.cursor()
    stationId = int(stationId)
    keys = list()
    for entry in dataPackage:
      if not keys:
        keys = list(entry.keys())
      
    pass

  # daten müssen weiter bereinigt werden.
  # Bsp 1: Anfrage von Darmstadt Hbf enthält TZ Rhein Main, Darmstadt
  # Bsp 2: Anfrage von TZ Rhein Main, Darmstadt enthält Darmstadt Hbf
  #        und Heinrich-Hertz-Straße, Darmstadt
  #  --> steht jeweils in der platform-Spalte und im Footer *DONE
  # Bsp 3: Zug startet in verschiedenen Bahnhöfen, wird aber offensichtlich 
  #        an einem Bahnhof zusammengeschlossen; erscheint aber weiterhin in der
  #        Liste als zwei Züg; wobei nur die Zugnummer nicht übereinstimmt.
  #        unbereinigt führt das dazu, dass eine solche Verspätung zweimal gemessen wird
  #  --> ??? (Entscheidung dokumentieren) 
  # Bsp 4: 

class Train:
  """
  is called with an url
  TODO: can also get its data from a database (redis) that is populated by the Stations-class
    -> idea: reference the row of redis-data and in the end call store with this data to store into a more permantent database
  """
  def __init__(self, url):
    self.url = url  # TODO: enthält datum und zeit und andere parameter: welche brauche ich und ergibt es sinn, diese zu verändern? (z.B. zeit anpassen)
    data = self.get(self.url)
    dataPackage = self.extractRelevantData(data)
  
  def get(self, url):
    response = requests.get(url)
    return response.text

  def extractRelevantData(self, data):
    parsedHtml = BeautifulSoup(data, "html.parser")
    # route rows -> dict (order is important)
    # route: 
    #   station, planedArrTime, planedDepTime, delayedArrTime, delayedDepTime, platformNumber, ,issues
    # Company:
    dataPackage = dict()
    dataPackage["route"] = dict()
    *companyRaw, = parsedHtml.find("div", "tqRemarks").stripped_strings
    for entry in companyRaw:
      if re.match(r"^Betreiber:", entry):
        company = entry.removeprefix("Betreiber:").strip()
        break
      else:
        company = None
    dataPackage["company"] = company

    routeRows = parsedHtml.find_all("div", class_=re.compile(r"tqRow trainrow_\d"))
    for index, row in enumerate(routeRows):
      dataPackage["route"][index] = dict()

      station = row.find("div", class_=re.compile("station")).find("a").string
      dataPackage["route"][index]["station"] = station

      arr = row.find("div", class_="arrival")
      arrTime = [s for s in arr.stripped_strings if re.search(r"\d{1,2}:\d{2}", s)]
      dataPackage["route"][index]["planedArrTime"] = arrTime[0].split(" ")[-1] if len(arrTime) > 0 else None
      dataPackage["route"][index]["delayedArrTime"] = arrTime[-1] if len(arrTime) > 1 else None

      dep = row.find("div", class_="departure")
      depTime = [s for s in dep.stripped_strings if re.search(r"\d{1,2}:\d{2}", s)]
      dataPackage["route"][index]["planedDepTime"] = depTime[0].split(" ")[-1] if len(depTime) > 0 else None
      dataPackage["route"][index]["delayedDepTime"] = depTime[-1] if len(depTime) > 1 else None

      platformRaw = row.find("div", class_="platform")
      platform = [s for s in platformRaw.stripped_strings if re.search(r"\d+", s)]
      dataPackage["route"][index]["platform"] = platform[0] if len(platform) > 0 else None

      issuesRaw = row.find("div", class_="ris")
      *issues, = issuesRaw.stripped_strings
      dataPackage["route"][index]["issues"] = dict()
      dataPackage["route"][index]["issues"]["canceled"] = "Halt entfällt" in issues
      issues = [s for s in issues if s not in ["Aktuelles", "Halt entfällt"]]
      dataPackage["route"][index]["issues"]["cause"] = issues[0] if len(issues) > 0 else None

    return dataPackage


    # TODO: use excessStations here as well 



if __name__ == "__main__":
  print("everything's fine")
  station0 = "Reinheim(Odenw)"
  station1 = "darmstadt+ost"
  station2 = "Frankfurt(Main)Hbf"
  station3 = "darmstadt+hbf"
  station4 = "Berlin+Hbf"
  station5 = "Hamburg+Hbf"
  station6 = "Lüneburg"
  station7 = "000100001"
  station8 = "8006006"
  # darmstadt = Station(station8)
  trainUrl = "https://reiseauskunft.bahn.de/bin/traininfo.exe/dn/450708/627868/187780/56347/81?ld=43158&country=DEU&protocol=https:&rt=1&date=20.12.23&time=13:37&station_evaId=104734&station_type=dep&"
  trainUrl = "https://reiseauskunft.bahn.de/bin/traininfo.exe/dn/747339/415855/215560/141333/81?ld=43158&country=DEU&protocol=https:&rt=1&date=20.12.23&time=13:37&station_evaId=8000068&station_type=dep&"
  trainUrl = "https://reiseauskunft.bahn.de/bin/traininfo.exe/dn/450708/627868/187780/56347/81?ld=43158&country=DEU&protocol=https:&rt=1&date=20.12.23&time=13:37&station_evaId=104734&station_type=dep&"
  trainUrl = "https://reiseauskunft.bahn.de/bin/traininfo.exe/dn/397068/313517/300536/17913/81?ld=43158&protocol=https:&rt=1&date=20.12.23&time=14:53&station_evaId=8000068&station_type=dep&"
  trainUrl = "https://reiseauskunft.bahn.de/bin/traininfo.exe/dn/836628/468438/43694/257029/81?ld=43158&protocol=https:&rt=1&date=20.12.23&time=15:04&station_evaId=8000105&station_type=dep&"
  trainUrl = "https://reiseauskunft.bahn.de/bin/traininfo.exe/dn/327147/314529/296484/39193/81?ld=43158&protocol=https:&rt=1&date=20.12.23&time=14:13&station_evaId=8000105&station_type=dep&"
  trainUrl = "https://reiseauskunft.bahn.de/bin/traininfo.exe/dn/478908/1274464/167130/76071/81?ld=43158&protocol=https:&rt=1&date=20.12.23&time=16:46&station_evaId=8000207&station_type=dep&"
  darmstadt = Train(trainUrl)
  

  