import json
import machine

class Handler:
    def __init__(self):
        pass

    def get(self, api_request):
        url_params = str(api_request['query_params'])
        url_params = url_params.strip("{")
        url_params = url_params.strip("}")
        url_params = url_params.replace("'", "")
        url_params = url_params.replace('"', '')
        url_params = url_params.split(", ")

        config = dict()
        confirmation = dict()

        for x in url_params:
            k, v = x.split(": ")
            config[k] = v

        with open('config.txt', 'w+') as f:

            for k, v in config.items():
                if k == "DatastoreFQDN":
                    v = v.replace("%3A", ":")
                    v = v.replace("%2F", "/")
                f.write(k + ": " + v + "\n")

        confirmation["Rebooting Mission Control"] = ("When it restarts, you'll be able to connect to the " + config["ap_ssid"] + " network you specified, and the board will be connected to your location's WiFi network. Please turn your machine off, wait a few seconds, and turn it back on again.")


        return confirmation
