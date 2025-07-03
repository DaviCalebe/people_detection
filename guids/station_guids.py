from datetime import datetime, time

STATION_SOURCE_P1 = '{D0116E62-874A-48E8-BC5A-4CAA4FA97D52}'  # 19:00 até 23:59
STATION_SOURCE_P2 = '{5451759A-2E12-473B-B2C1-3D6422266194}'  # 00:00 até 07:00

now = datetime.now().time()

STATION_BASE_URL = 'http://10.10.50.22:8081/api'

STATION_PEOPLE_DETECTION_EVENT = '{F6DFC618-615A-4DFD-AC86-46670FCA8529}'

STATION_SOURCE_FULLTIME = '{A324B57D-1BDA-4B7D-8BB7-A6B9A545E06E}'


def get_station_source():
    now = datetime.now().time()
    print(now)
    if time(19, 0) <= now <= time(23, 59):
        return STATION_SOURCE_P1
    elif time(0, 0) <= now <= time(7, 0):
        return STATION_SOURCE_P2
    else:
        return None
