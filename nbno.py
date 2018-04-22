# -*- coding: utf-8 -*- 
import io, urllib2, os, argparse
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
    elif (bokavis=='avis'):
      self.URLpart = 'http://www.nb.no/services/image/resolver?url_ver=geneza&urn=URN:NBN:no-nb_digavis_'
      self.URLsep1 = '-1_'
      self.URLsep2 = '_null'
    else:
      print 'Du mangler å sette type!'
      exit()

  def newURL(self, side, col, row):
    self.side = str(side)
    self.col = int(col)
    self.row = int(row)
    self.updateURL()
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
        break
      else:
        c+=1
    while True:
      xUrl = self.newURL(side,'0',r)
      try:
        req = urllib2.Request(xUrl, headers={ 'User-Agent': 'Mozilla/5.0' })
        response = urllib2.urlopen(req)
      except urllib2.HTTPError as e:
        r-=1
        break
      else:
        r+=1
    self.maxcol = int(c)
    self.maxrow = int(r)
    return str(c)+str(r)

def downloadPage(pageNum,bok):
  imageParts = []
  maxWidth, maxHeight = 0,0
  r=0
  while (r<=bok.maxrow):
    c=0
    while (c<=bok.maxcol):
      url = bok.newURL(pageNum,c,r)
      try:
        req = urllib2.Request(url, headers={ 'User-Agent': 'Mozilla/5.0' })
        response = urllib2.urlopen(req).read()
      except urllib2.HTTPError as e:
        error = e #munch
      else:
        img = Image.open(io.BytesIO(response))
        imageParts.append(img)
        if (r==0):
          maxWidth+=img.size[0]
        if (c==0):
          maxHeight+=img.size[1]
      c+=1
    r+=1
  if (len(imageParts)==0):
    print 'Ferdig med å laste ned alle sider.'
    exit()
  else:
    sinWidth, sinHeight = imageParts[0].size
    newImg = Image.new('RGB', (maxWidth,maxHeight))
    r=0
    partCount=0
    while (r<=bok.maxrow):
      c=0
      while (c<=bok.maxcol):
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
optional.add_argument('--start', metavar='<int>', help='Sidetall å starte på', default=False)
optional.add_argument('--stop', metavar='<int>', help='Sidetall å stoppe på', default=False)
optional.add_argument('--level', metavar='<int>', help='Sett Level', default=False)
optional.add_argument('--maxlevel', metavar='<int>', help='Sett MaxLevel', default=False)
parser._action_groups.append(optional)
args = parser.parse_args()

if args.id:
  x = theURL(str(args.id))
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
    x.updateMaxColRow('001')
  else:  
    x.setType('bok')
    print 'Laster ned bok med ID: '+str(args.id)
    x.updateMaxColRow('C1')
    downloadPage('C1',x)
    x.updateMaxColRow('C2')
    downloadPage('C2',x)
    x.updateMaxColRow('C3')
    downloadPage('C3',x)
    x.updateMaxColRow('0001')
  if args.start:
    pageCounter = int(args.start)
  else:
    pageCounter = 1
  if args.stop:
    stopPage = int(args.stop)
  else:
    stopPage = 9999
  while True:
    if args.avis:
      downloadPage(str(pageCounter).rjust(3, '0'),x)
    else:  
      downloadPage(str(pageCounter).rjust(4, '0'),x)
    if (pageCounter == stopPage):
      print 'Ferdig med å laste ned alle sider.'
      exit()
    pageCounter+=1
else:
    parser.print_help()
    exit()
