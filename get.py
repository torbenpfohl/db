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

# starten mit einer leichten datenbank - splite?

from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
import re

class Station:
  def __init__(self, name):
    self.name = name
    requestTimeDate = datetime.now()
    self.requestDate = requestTimeDate.strftime("%d.%m.%y")
    self.requestTime = requestTimeDate.strftime("%H:%M")
    #self.requestDate = "03.09.23"  #test
    #self.requestTime = "23:44"     #test
    self.htmlDocument = self.getData()
    self.dataPacket = self.extractRelevantData(self.htmlDocument)
    self.storeData(self.dataPacket)


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

    # extract data from rows and validate those rows

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
    print(otherStations)

    allRows = parsedHtml.find_all("tr", id=re.compile("^journeyRow_\d+"))

    print("Entries:", len(allRows))

    # reverse through allRows because this way I can validate the planedTime
    #   and therefore calculate the delayedTime here too 
    planedTimeBefore = None
    for row in reversed(allRows):
      # do platform in the beginning because the row might not belong to the
      # requested station 
      platform = "".join([word for word in row.find("td", "platform").stripped_strings])
      platform = platform[1:] if platform.startswith("-") else platform
      platformStationMatch = re.search(r"^\d*", platform)
      platformStation = None
      if platformStationMatch:
        platform = platformStationMatch.group()
        platformStation = platform.replace(platformStationMatch.group(), "")
      if platformStation and platformStation in otherStations:
        continue

      planedTime = str(row.find("td", "time").string)
      # transform planedTime to datetime-object
      if rowDate == 2:
        planedTime = datetime.strptime(planedTime+" "+dates[-1], "%H:%M %d.%m.%y")
        if planedTimeBefore:
          diff = planedTimeBefore - planedTime
          if diff.total_seconds() < 0:
            planedTime -= timedelta(days=1)
      else:
        planedTime = datetime.strptime(planedTime+" "+self.requestDate, "%H:%M %d.%m.%y")
      planedTimeBefore = planedTime

      transportationTypePicUrl = row.find("td", "train").a.img["src"]
      transportationType = re.search("(?<=/)[a-z_]+(?=_\d+x\d+.[a-z]+$)", transportationTypePicUrl).group()
      transportationType = str(transportationType)
      trainNameField = row.find_all("td", "train")[-1]
      trainUrl = "https://reiseauskunft.bahn.de" + str(trainNameField.a["href"])
      trainName = [re.compile(r"\s+").sub(" ", word) for word in trainNameField.stripped_strings]
      trainName = " ".join(trainName)
      route = row.find("td", "route")
      endstation = str("".join([word for word in route.span.a.stripped_strings]))

      issues = row.find("td", "ris")
      issuesText = "".join([word for word in issues.stripped_strings])
      delayedTime = None
      delayCause = None
      delayedBy = None
      if len(issuesText) != 0:
        delayed = True
        # also search for a new time, like a new date (if present)
        delayedTimeMatch = re.search(r"\d{2}:\d{2}", issuesText)
        if delayedTimeMatch:
          delayedTime = delayedTimeMatch.group()
          delayCause = issuesText.replace(delayedTime, "")
          # delayed by
          #   if date is not avalable with the issuesText, than it will be
          #   obvious while calculation the delayed by value (because it will
          #   be negative)
          hours, minutes = delayedTime.split(":")
          delayedTime = planedTime.replace(hour=int(hours), minute=int(minutes))
          delayedBy = delayedTime - planedTime
          if delayedBy.total_seconds() == 0:
            delayed = False
          elif delayedBy.total_seconds() < 0:
            delayedTime += timedelta(days=1)
            delayedBy += timedelta(days=1)
        else:
          delayed = True
          delayCause = issuesText
      else:
        delayed = False

      # if delayed:
        # print(planedTime, delayed, repr(delayCause), delayedTime, delayedBy)

      delayOnTime_dbClass = "delayOnTime" in issues.span["class"] if issues.span else None

    # turn text/NavigableString (zugplan, bahnsteig, etc.) with unicode() or str() into standalone text

    # wie organisiere ich die daten? 
    return  # ein datenpaket
  
  # determine next call-/query-time
  
  def storeData(self, dataPacket):
    # metadaten speichern (abfragezeit, ?)
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


if __name__ == "__main__":
  print("everything's fine")
  station0 = "Reinheim(Odenw)"
  station1 = "darmstadt+ost"
  station2 = "Frankfurt(Main)Hbf"
  station3 = "darmstadt+hbf"
  station4 = "Berlin+Hbf"
  station5 = "Hamburg+Hbf"
  station6 = "Lüneburg"
  darmstadt = Station(station0)
  