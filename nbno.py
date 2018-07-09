# -*- coding: utf-8 -*- 
import io, urllib2, os, argparse, glob
from PIL import Image

class theURL():
  def __init__(self, bokID):
    self.bokID = str(bokID)
    self.side = '0001'
    self.level = 5
    self.maxLevel = 5
    self.col = 0
    self.maxcol = 0
    self.row = 0
    self.maxrow = 0
    self.printUrl = False
    self.printError = False
    self.resX = '9999'
    self.resY = '9999'
    self.tileWidth = '1024'
    self.tileHeight = '1024'
    self.URL = ''
    self.URLpart = ''
    self.URLsep1 = ''
    self.URLsep2 = ''
  
  def setLevel(self, level):
    self.level = int(level)

  def setMaxLevel(self, maxLevel):
    self.maxLevel = int(maxLevel)

  def setMaxCol(self, maxCol):
    self.maxcol = int(maxCol)

  def setMaxRow(self, maxRow):
    self.maxrow = int(maxRow)

  def setPrintUrl(self):
    self.printUrl = True

  def setPrintError(self):
    self.printError = True

  def updateURL(self):
    self.URL = self.URLpart+\
    str(self.bokID)+self.URLsep1+self.side+self.URLsep2+\
    '&maxLevel='+str(self.maxLevel)+'&level='+str(self.level)+\
    '&col='+str(self.col)+'&row='+str(self.row)+\
    '&resX='+str(self.resX)+'&resY='+str(self.resY)+\
    '&tileWidth='+str(self.tileWidth)+'&tileHeight='+str(self.tileWidth)
  
  def setType(self, bokavis):
    if (bokavis=='bok'):
      self.URLpart = 'http://www.nb.no/services/image/resolver?url_ver=geneza&urn=URN:NBN:no-nb_digibok_'
      self.URLsep1 = '_'
      self.URLsep2 = ''
    elif (bokavis=='avis'):
      self.URLpart = 'http://www.nb.no/services/image/resolver?url_ver=geneza&urn=URN:NBN:no-nb_digavis_'
      self.URLsep1 = '-1_'
      self.URLsep2 = '_null'
    else:
      print 'Feil type!'
      exit()

  def newURL(self, side, col, row):
    self.side = str(side)
    self.col = int(col)
    self.row = int(row)
    self.updateURL()
    if self.printUrl:
      print self.URL
    return self.URL

  def updateMaxColRow(self, side):
    c,r = 0,0
    while True:
      xUrl = self.newURL(side,c,'0')
      try:
        req = urllib2.Request(xUrl, headers={ 'User-Agent': 'Mozilla/5.0' })
        response = urllib2.urlopen(req)
      except urllib2.HTTPError as e:
        c-=1
        if self.printError:
          print e
        break
      else:
        c+=1
    while True:
      xUrl = self.newURL(side,'0',r)
      try:
        req = urllib2.Request(xUrl, headers={ 'User-Agent': 'Mozilla/5.0' })
        response = urllib2.urlopen(req)
      except urllib2.HTTPError as e:
        if self.printError:
          print e
        r-=1
        break
      else:
        r+=1
    self.maxcol = int(c)
    self.maxrow = int(r)

def downloadPage(pageNum,bok):
  imageParts = []
  maxWidth, maxHeight = 0,0
  numrow, numcol = 0,0
  r=0
  while (r<=bok.maxrow):
    c=0
    while (c<=bok.maxcol):
      url = bok.newURL(pageNum,c,r)
      try:
        req = urllib2.Request(url, headers={ 'User-Agent': 'Mozilla/5.0' })
        response = urllib2.urlopen(req).read()
      except urllib2.HTTPError as e:
        if bok.printError:
          print e
      else:
        try:
          img = Image.open(io.BytesIO(response))
          imageParts.append(img)
          if (r==0):
            maxWidth+=img.size[0]
            numcol +=1
          if (c==0):
            maxHeight+=img.size[1]
            numrow +=1
        except IOError as e:
          if bok.printError:
            print e
      c+=1
    r+=1
  if (len(imageParts)==0):
    print 'Ferdig med å laste ned alle sider.'
    return False
  else:
    sinWidth, sinHeight = imageParts[0].size
    newImg = Image.new('RGB', (maxWidth,maxHeight))
    r=0
    partCount=0
    numrow,numcol = (numrow-1),(numcol-1)
    while (r<=numrow):
      c=0
      while (c<=numcol):
        newImg.paste(imageParts[partCount], ((c*sinWidth),(r*sinHeight)))
        partCount+=1
        c+=1
      r+=1
    newImg.save(folder+str(pageNum)+'.jpg')
    print 'Lagret side '+pageNum+'.jpg'

parser = argparse.ArgumentParser()
optional = parser._action_groups.pop()
required = parser.add_argument_group('required arguments')
required.add_argument('--id', metavar='<bokID>', help='IDen på boken som skal lastes ned', default=False)
optional.add_argument('--avis', action='store_true', help='Settes om det er en avis som lastes', default=False)
optional.add_argument('--cover', action='store_true', help='Settes for å laste covers', default=False)
optional.add_argument('--pdf', action='store_true', help='Settes for å lage pdf av bildene som lastes', default=False)
optional.add_argument('--f2pdf', action='store_true', help='Settes for å lage pdf av bilder i mappe', default=False)
optional.add_argument('--url', action='store_true', help='Settes for å printe URL av hver del', default=False)
optional.add_argument('--error', action='store_true', help='Settes for å printe feilkoder', default=False)
optional.add_argument('--start', metavar='<int>', help='Sidetall å starte på', default=False)
optional.add_argument('--stop', metavar='<int>', help='Sidetall å stoppe på', default=False)
optional.add_argument('--level', metavar='<int>', help='Sett Level', default=False)
optional.add_argument('--maxlevel', metavar='<int>', help='Sett MaxLevel', default=False)
optional.add_argument('--maxcol', metavar='<int>', help='Sett MaxCol', default=False)
optional.add_argument('--maxrow', metavar='<int>', help='Sett MaxRow', default=False)
parser._action_groups.append(optional)
args = parser.parse_args()

if args.id:
  if args.f2pdf:
    filelist = []
    filelist.extend(glob.glob(os.path.join(str(args.id),('[0-9]'*4)+'.jpg')))
    filelist = sorted(filelist)
    print 'Lager ' + str(args.id) + '.pdf'
    Image.open(filelist[0]).save(str(args.id)+'.pdf', resolution=100.0)
    print str(filelist[0]) + ' --> ' + str(args.id) + '.pdf'
    for file in filelist[1:]:
      Image.open(file).save(str(args.id)+'.pdf', resolution=100.0, append=True)
      print str(file) + ' --> ' + str(args.id) + '.pdf'
    print 'Ferdig med å lage pdf.
    exit()
  x = theURL(str(args.id))
  if args.start:
    pageCounter = int(args.start)
  else:
    pageCounter = 1
  if args.stop:
    stopPage = int(args.stop)
  else:
    stopPage = 9999
  if args.url:
    x.setPrintUrl()
  if args.error:
    x.setPrintError()
  if args.level:
    x.setLevel(int(args.level))
  if args.maxlevel:
    x.setMaxLevel(int(args.maxlevel))
  folder = '.'+os.path.sep+str(x.bokID)+os.path.sep
  try:
    os.stat(folder)
  except:
    os.mkdir(folder)
  if args.avis:
    x.setType('avis')
    print 'Laster ned avis med ID: '+str(args.id)
    x.updateMaxColRow(str(pageCounter).rjust(3, '0'))
  else:  
    x.setType('bok')
    print 'Laster ned bok med ID: '+str(args.id)
    if args.cover:
      x.updateMaxColRow('C1')
      downloadPage('C1',x)
      x.updateMaxColRow('C2')
      downloadPage('C2',x)
      x.updateMaxColRow('C3')
      downloadPage('C3',x)
    x.updateMaxColRow(str(pageCounter).rjust(4, '0'))
  if args.maxcol:
    x.setMaxCol(int(args.maxcol))
  if args.maxrow:
    x.setMaxRow(int(args.maxrow))
  while True:
    if args.avis:
      down = downloadPage(str(pageCounter).rjust(3, '0'),x)
    else:  
      down = downloadPage(str(pageCounter).rjust(4, '0'),x)
    if (down == False):
      break
    if args.pdf:
      try:
        Image.open(folder+x.side+'.jpg').save(str(args.id)+'.pdf', 'PDF',resolution=100.0, append=True)
      except:
        if args.cover:
          Image.open(folder+'C1.jpg').save(str(args.id)+'.pdf', 'PDF',resolution=100.0)
          Image.open(folder+x.side+'.jpg').save(str(args.id)+'.pdf', 'PDF',resolution=100.0, append=True)
        else:
       	  Image.open(folder+x.side+'.jpg').save(str(args.id)+'.pdf', 'PDF',resolution=100.0)
    if (pageCounter == stopPage):
      print 'Ferdig med å laste ned alle sider.'
      break
    pageCounter+=1
  exit()
else:
    parser.print_help()
    exit()
