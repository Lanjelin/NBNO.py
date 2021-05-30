# NBNO.py v2
Dette er et Python script som laster ned bøker og annet media fra Nasjonalbiblioteket (NB.no).


For å kjøre denne koden trengs Python 3.7 eller nyere, og pillow.
For å sjekke versjon av python, kjør **python --version**, eventuelt **python3 --version** fra kommandolinjen.

Python 3 kan lastes ned fra https://www.python.org/downloads/ Pillow legges til ved å kjøre **pip install "pillow>6.0"** eller **easy_install "pillow>6.0"** etter python er installert (Husk å få med at Python skal oppdatere Path).

For Python 2.7 kan nbno27.py brukes, men Python 2.7 når end-of-life 1. Januar 2020.
Denne versjonen av koden vil derfor ikke vedlikeholdes.

For å kjøre scriptet er kommandoen rimelig enkel, det eneste påkrevde argumentet er ID, som finnes ved å trykke Referere/Sitere for så å kopiere alt av tekst og tall etter no-nb_ eks. digitidsskrift_202101..etc

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
```
bruk: nbno.py [-h] [--id <bokID>] [--cover] [--pdf] [--f2pdf]
              [--url] [--error] [--start <int>] [--stop <int>]

påkrevd argument:
  --id <bokID>    IDen på boken som skal lastes ned

valgfrie argumenter:
  -h, --help      show this help message and exit
  --cover         Settes for å laste covers
  --pdf           Settes for å lage pdf av bildene som lastes
  --f2pdf         Settes for å lage pdf av bilder i mappe
  --url           Settes for å printe URL på hver del
  --error         Settes for å printe HTTP feilkoder
  --start <int>   Sidetall å starte på
  --stop <int>    Sidetall å stoppe på
```
