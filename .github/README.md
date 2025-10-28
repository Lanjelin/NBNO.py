# NBNO.py

<p align="center">
  <img src="https://raw.githubusercontent.com/Lanjelin/NBNO.py/refs/heads/master/web/static/img/logo.png" width="300" alt="Logo">
</p>

---

Dette er et Python script som laster ned bøker og annet media fra Nasjonalbiblioteket (NB.no).

### Kjøring i Docker - Web

<details>
  <summary><strong>Screenshot</strong></summary>
  <p align="center">
    <a href=https://github.com/Lanjelin/NBNO.py/blob/master/.github/screenshots/fullpage.png>
    <img src="https://raw.githubusercontent.com/Lanjelin/NBNO.py/refs/heads/master/.github/screenshots/fullpage.png"
         alt="Full-page screenshot preview"  width="600"/>
    </a>
  </p>
</details>


Bind en lokal mappe til `/data` for å få tilgang til filer som lastes ned via utforsker, filene er ellers tilgjengelige via webgrensesnittet.  
Om en ønsker flere språk enn Norsk og Engelsk for ORC, må en binde en lokal mappe til `/opt/tessdata` og plassere [*.traineddata](https://github.com/tesseract-ocr/tessdata) der.  

Ellers er det bare å starte containeren, og peke nettlesen til [port 5000](http://127.0.0.1:5000).

For å finne medie-ID, ta en kikk [her](https://github.com/Lanjelin/NBNO.py/blob/master/.github/screenshots/medie_id.png)

#### Docker Run
`docker run --name nbno -p 5000:5000 -v ./nbno/data:/data -v ./nbno/tessdata:/opt/tessdata -d ghcr.io/lanjelin/nbnopy:latest`

#### Docker compose
```yaml
services:
  nbnopy:
    container_name: nbno
    ports:
      - 5000:5000
    volumes:
      - ./nbno/data:/data
      - ./nbno/tessdata:/opt/tessdata
    image: ghcr.io/lanjelin/nbnopy:latest
```


### Kjøring uten Docker - CLI
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

<details>
  <summary>Innlogget innhold</summary>
  Som innlogget, åpne boka der en kan lese den, åpne Utviklerverktøy og finn Nettverkfanen.  
  Refresh siden, og nettverksfanen populeres med innhold.  
  Finn og velg manifest?fields=etcetc i listen, og bla igjen ned og finn Request Headers.  

  Her kopieres innholdet fra authorization og cookie og lagres i en textfil ved scriptet.  
  Formaten på tekstfilen er
  ```
  authorization=4JjcVi6faGF-GhD6wMoXZ80rUkg.*AAJTSQACMDIAAlNLABxxRandomRandomxxSNVpvUTlQxxRandomRandomxxDVFMAAlMxAAIwMQ..
  cookie=_ga=GA1.1.1234543217.123454321; _hjSessionUser_123454321=eyJpZCI6IjUzOTZmxxRandomRandomxxy1hNDEwLTc0ZjA4NTJhxxRandomRandomxxOjE3MjYwNTEyNzcxxRandomRandomxxW5nIjp0cnVlfQ==;osvosvetc
  ```
  Scriptet kjøres deretter med `--cookie` flagget som peker til filen, feks `python3 nbno.py --id blabla --cookie nbno-cookie.txt`

</details>

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
  --cookie <string>  Sti til fil for autentisering
```

