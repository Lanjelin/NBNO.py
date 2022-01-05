# NBNO.py
Dette er et Python script som laster ned bøker og annet media fra Nasjonalbiblioteket (NB.no).


For å kjøre denne koden trengs Python 3.7 eller nyere, pillow og requests.

Linux og Mac kommer normalt med python installert.
For Windows, last ned Python fra [python.org](https://www.python.org/downloads/), få med 'Add Python 3.xx to PATH'

For å sjekke versjon av python, kjør `python --version`(Windows), `python3 --version`(Mac/Linux), fra kommandolinjen.

For å installere pillow og requests, kjør `python3 -m pip install -r requirements.txt` fra samme mappen de nedlastede filene herfra ligger.

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
bruk: nbno.py [-h] [--id <ID>] [--cover] [--pdf] [--f2pdf]
              [--url] [--error] [--start <int>] [--stop <int>]

påkrevd argument:
  --id <ID>    IDen på innholdet som skal lastes ned

valgfrie argumenter:
  -h, --help      show this help message and exit
  --cover         Settes for å laste covers
  --pdf           Settes for å lage pdf av bildene som lastes
  --f2pdf         Settes for å lage pdf av bilder i eksisterende mappe
  --url           Settes for å printe URL på hver del
  --error         Settes for å printe HTTP feilkoder
  --start <int>   Sidetall å starte på
  --stop <int>    Sidetall å stoppe på
```
