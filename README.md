# NBNO.py
NB.no nedlaster


For å kjøre denne koden trengs Python 2.7 og pillow.
For å sjekke om du har python 2.7, kjør **python --version** fra kommandolinjen.

Python 2.7 kan lastes ned fra https://www.python.org/download/releases/2.7/ og Pillow kan lastes ned vha. **pip install pillow** eller **easy_install pillow**

Kommandoer for å kjøre

```
bruk: nbno.py [-h] [--id <bokID>] [--start <int>] [--stop <int>]
               [--level <int>] [--maxlevel <int>]

påkrevd argument:
  --id <bokID>    IDen på boken som skal lastes ned

valgfrie argumenter:
  -h, --help      show this help message and exit
  --start <int>   Sidetall å starte på
  --stop <int>    Sidetall å stoppe på
  --level <int>   Sett Level
  --maxlevel <n>  Sett MaxLevel
```
