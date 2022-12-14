# Vue Energy Data Fetcher

This module queries the Emporia API to get summary usage for all tracked devices
over every 15-minute period in the last day. If DB information is configured,
it inserts the results into the database. If not, it prints the results as a CSV.

#### Install process

```bash
git clone https://github.com/jonwedell/EmporiaDataFetcher.git
cd EmporiaDataFetcher
./setup.sh
``` 

Then create a file named `config.json` in your EmporiaDataFetcher directory and
enter your configuration. You can copy `config_example.json` to `config.json` for
a starting point. If a database is configured, it will attempt to store results
in the database when executed. Regardless, it will print results to the terminal
in CSV.

#### To Run

Interactively:

```bash
source venv/bin/activate
./vced_stats.py
```

If executing from a crontab or similar environment (make sure to replace the
relative path shown below with an absolute path - replacing `.` with whatever
the path to the EmporiaDataFetcher directory is):

```bash
./venv/bin/python3 vced_stats.py
```
