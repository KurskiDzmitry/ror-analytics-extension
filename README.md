# ror-analytics-extension
## Description
Python script for generation RoR extension files (POC).
### Input: 
JSON Schema files placed in the `Schema` folder.
### Output: 
- Sources/Extension folder: `RAnalyticsRATTracker` extension file with API and `PayloadValidator` file.
- Sources/ObjectModel folder: file with `Struct` generated from JSON Schema file.
  
## Requirements
Python 3.

## Build & Run
- Navigate to `ror-analytics-extension` folder.
- Run `python3 extension_generator.py` command in the terminal.
