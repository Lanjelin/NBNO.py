# NBNO.py
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

Dette er et Python script som laster ned bøker og annet media fra Nasjonalbiblioteket (NB.no).

### Kjøring i Docker
Bind en lokal mappe til `/data` for å få tilgang til filer som lastes ned.  
Argumenter nevnt nedenfor legges til forløpende på slutten av f.eks følgende:  
`docker run --rm -v /home/nbno/nbno/:/data ghcr.io/lanjelin/nbnopy:latest --id digibok_200709..etc --title --pdf`  

### Kjøring uten Docker
For å kjøre denne koden trengs Python 3.7 eller nyere, pillow og requests.

Linux og Mac kommer normalt med python installert.
For Windows, last ned Python fra [python.org](https://www.python.org/downloads/), få med 'Add Python 3.xx to PATH'

For å sjekke versjon av python, kjør `python --version`(Windows), `python3 --version`(Mac/Linux), fra kommandolinjen.

For å installere pillow og requests, kjør `python3 -m pip install -r requirements.txt` fra samme mappen de nedlastede filene herfra ligger.

### Argumenter
Eneste påkrevde argumentet er ID, som finnes ved å trykke Referere/Sitere for så å kopiere alt av tekst og tall etter no-nb_ eks. digitidsskrift_202101..etc --> `python3 nbno.py --id digitidsskrift_202101..etc`

Følgende er støttet:
 - Bøker (digibok)
 - Aviser (digavis)
 - Bilder (digifoto)
 - Tidsskrift (digitidsskrift)
 - Kart (digikart)
 - Brev og Manuskripter (digimanus)
 - Noter (digibok)
 - Musikkmanuskripter (digimanus)
 - Plakater (digifoto)
 - Programrapport (digiprogramrapport)
```
bruk: nbno.py [-h] [--id <ID>] [--cover] [--pdf] [--f2pdf] [--url] [--error] 
              [--v] [--resize <int>] [--start <int>] [--stop <int>]

påkrevd argument:
  --id <ID>    IDen på innholdet som skal lastes ned

valgfrie argumenter:
  -h, --help      show this help message and exit
  --cover         Settes for å laste covers
  --title         Settes for å hente tittel på bok automatisk
  --pdf           Settes for å lage pdf av bildene som lastes
  --f2pdf         Settes for å lage pdf av bilder i eksisterende mappe
  --url           Settes for å printe URL på hver del
  --error         Settes for å printe HTTP feilkoder
  --v             Settes for å printe mer info
  --resize <int>  Prosent av originalstørrelse på bilder
  --start <int>   Sidetall å starte på
  --stop <int>    Sidetall å stoppe på
```
