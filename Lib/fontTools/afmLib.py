"""Module for reading and writing AFM files."""

# XXX reads AFM's generated by Fog, not tested with much else.
# It does not implement the full spec (Adobe Technote 5004, Adobe Font Metrics
# File Format Specification). Still, it should read most "common" AFM files.

import re

__version__ = "$Id: afmLib.py,v 1.6 2003-05-24 12:50:47 jvr Exp $"


# every single line starts with a "word"
identifierRE = re.compile("^([A-Za-z]+).*")

# regular expression to parse char lines
charRE = re.compile(
		"(-?\d+)"			# charnum
		"\s*;\s*WX\s+"		# ; WX 
		"(-?\d+)"			# width
		"\s*;\s*N\s+"		# ; N 
		"([.A-Za-z0-9_]+)"	# charname
		"\s*;\s*B\s+"		# ; B 
		"(-?\d+)"			# left
		"\s+"				# 
		"(-?\d+)"			# bottom
		"\s+"				# 
		"(-?\d+)"			# right
		"\s+"				# 
		"(-?\d+)"			# top
		"\s*;\s*"			# ; 
		)

# regular expression to parse kerning lines
kernRE = re.compile(
		"([.A-Za-z0-9_]+)"	# leftchar
		"\s+"				# 
		"([.A-Za-z0-9_]+)"	# rightchar
		"\s+"				# 
		"(-?\d+)"			# value
		"\s*"				# 
		)

# regular expressions to parse composite info lines of the form:
# Aacute 2 ; PCC A 0 0 ; PCC acute 182 211 ;
compositeRE = re.compile(
		"([.A-Za-z0-9_]+)"	# char name
		"\s+"				# 
		"(\d+)"				# number of parts
		"\s*;\s*"			# 
		)
componentRE = re.compile(
		"PCC\s+"			# PPC
		"([.A-Za-z0-9_]+)"	# base char name
		"\s+"				# 
		"(-?\d+)"			# x offset
		"\s+"				# 
		"(-?\d+)"			# y offset
		"\s*;\s*"			# 
		)

preferredAttributeOrder = [
		"FontName",
		"FullName",
		"FamilyName",
		"Weight",
		"ItalicAngle",
		"IsFixedPitch",
		"FontBBox",
		"UnderlinePosition",
		"UnderlineThickness",
		"Version",
		"Notice",
		"EncodingScheme",
		"CapHeight",
		"XHeight",
		"Ascender",
		"Descender",
]


class error(Exception): pass


class AFM:
	
	_attrs = None
	
	_keywords = ['StartFontMetrics',
			'EndFontMetrics',
			'StartCharMetrics',
			'EndCharMetrics',
			'StartKernData',
			'StartKernPairs',
			'EndKernPairs',
			'EndKernData',
			'StartComposites',
			'EndComposites',
			]
	
	def __init__(self, path=None):
		self._attrs = {}
		self._chars = {}
		self._kerning = {}
		self._index = {}
		self._comments = []
		self._composites = {}
		if path is not None:
			self.read(path)
	
	def read(self, path):
		lines = readlines(path)
		for line in lines:
			if not line.strip():
				continue
			m = identifierRE.match(line)
			if m is None:
				raise error("syntax error in AFM file: " + repr(line))
			
			pos = m.regs[1][1]
			word = line[:pos]
			rest = line[pos:].strip()
			if word in self._keywords:
				continue
			if word == "C":
				self.parsechar(rest)
			elif word == "KPX":
				self.parsekernpair(rest)
			elif word == "CC":
				self.parsecomposite(rest)
			else:
				self.parseattr(word, rest)
	
	def parsechar(self, rest):
		m = charRE.match(rest)
		if m is None:
			raise error("syntax error in AFM file: " + repr(rest))
		things = []
		for fr, to in m.regs[1:]:
			things.append(rest[fr:to])
		charname = things[2]
		del things[2]
		charnum, width, l, b, r, t = (int(thing) for thing in things)
		self._chars[charname] = charnum, width, (l, b, r, t)
	
	def parsekernpair(self, rest):
		m = kernRE.match(rest)
		if m is None:
			raise error("syntax error in AFM file: " + repr(rest))
		things = []
		for fr, to in m.regs[1:]:
			things.append(rest[fr:to])
		leftchar, rightchar, value = things
		value = int(value)
		self._kerning[(leftchar, rightchar)] = value
	
	def parseattr(self, word, rest):
		if word == "FontBBox":
			l, b, r, t = [int(thing) for thing in rest.split()]
			self._attrs[word] = l, b, r, t
		elif word == "Comment":
			self._comments.append(rest)
		else:
			try:
				value = int(rest)
			except (ValueError, OverflowError):
				self._attrs[word] = rest
			else:
				self._attrs[word] = value
	
	def parsecomposite(self, rest):
		m = compositeRE.match(rest)
		if m is None:
			raise error("syntax error in AFM file: " + repr(rest))
		charname = m.group(1)
		ncomponents = int(m.group(2))
		rest = rest[m.regs[0][1]:]
		components = []
		while True:
			m = componentRE.match(rest)
			if m is None:
				raise error("syntax error in AFM file: " + repr(rest))
			basechar = m.group(1)
			xoffset = int(m.group(2))
			yoffset = int(m.group(3))
			components.append((basechar, xoffset, yoffset))
			rest = rest[m.regs[0][1]:]
			if not rest:
				break
		assert len(components) == ncomponents
		self._composites[charname] = components
	
	def write(self, path, sep='\r'):
		import time
		lines = [	"StartFontMetrics 2.0",
				"Comment Generated by afmLib, version %s; at %s" % 
						(__version__.split()[2],
						time.strftime("%m/%d/%Y %H:%M:%S", 
						time.localtime(time.time())))]
		
		# write comments, assuming (possibly wrongly!) they should
		# all appear at the top
		for comment in self._comments:
			lines.append("Comment " + comment)
		
		# write attributes, first the ones we know about, in
		# a preferred order
		attrs = self._attrs
		for attr in preferredAttributeOrder:
			if attr in attrs:
				value = attrs[attr]
				if attr == "FontBBox":
					value = "%s %s %s %s" % value
				lines.append(attr + " " + str(value))
		# then write the attributes we don't know about,
		# in alphabetical order
		items = sorted(attrs.items())
		for attr, value in items:
			if attr in preferredAttributeOrder:
				continue
			lines.append(attr + " " + str(value))
		
		# write char metrics
		lines.append("StartCharMetrics " + repr(len(self._chars)))
		items = [(charnum, (charname, width, box)) for charname, (charnum, width, box) in self._chars.items()]
		
		def myCmp(a, b):
			"""Custom compare function to make sure unencoded chars (-1) 
			end up at the end of the list after sorting."""
			if a[0] == -1:
				a = (0xffff,) + a[1:]  # 0xffff is an arbitrary large number
			if b[0] == -1:
				b = (0xffff,) + b[1:]
			return cmp(a, b)
		items.sort(myCmp)
		
		for charnum, (charname, width, (l, b, r, t)) in items:
			lines.append("C %d ; WX %d ; N %s ; B %d %d %d %d ;" %
					(charnum, width, charname, l, b, r, t))
		lines.append("EndCharMetrics")
		
		# write kerning info
		lines.append("StartKernData")
		lines.append("StartKernPairs " + repr(len(self._kerning)))
		items = self._kerning.items()
		items.sort()		# XXX is order important?
		for (leftchar, rightchar), value in items:
			lines.append("KPX %s %s %d" % (leftchar, rightchar, value))
		lines.append("EndKernPairs")
		lines.append("EndKernData")
		
		if self._composites:
			composites = sorted(self._composites.items())
			lines.append("StartComposites %s" % len(self._composites))
			for charname, components in composites:
				line = "CC %s %s ;" % (charname, len(components))
				for basechar, xoffset, yoffset in components:
					line = line + " PCC %s %s %s ;" % (basechar, xoffset, yoffset)
				lines.append(line)
			lines.append("EndComposites")
		
		lines.append("EndFontMetrics")
		
		writelines(path, lines, sep)
	
	def has_kernpair(self, pair):
		return pair in self._kerning
	
	def kernpairs(self):
		return self._kerning.keys()
	
	def has_char(self, char):
		return char in self._chars
	
	def chars(self):
		return self._chars.keys()
	
	def comments(self):
		return self._comments
	
	def addComment(self, comment):
		self._comments.append(comment)
	
	def addComposite(self, glyphName, components):
		self._composites[glyphName] = components
	
	def __getattr__(self, attr):
		if attr in self._attrs:
			return self._attrs[attr]
		else:
			raise AttributeError(attr)
	
	def __setattr__(self, attr, value):
		# all attrs *not* starting with "_" are consider to be AFM keywords
		if attr[:1] == "_":
			self.__dict__[attr] = value
		else:
			self._attrs[attr] = value
	
	def __delattr__(self, attr):
		# all attrs *not* starting with "_" are consider to be AFM keywords
		if attr[:1] == "_":
			try:
				del self.__dict__[attr]
			except KeyError:
				raise AttributeError(attr)
		else:
			try:
				del self._attrs[attr]
			except KeyError:
				raise AttributeError(attr)
	
	def __getitem__(self, key):
		if isinstance(key, tuple):
			# key is a tuple, return the kernpair
			return self._kerning[key]
		else:
			# return the metrics instead
			return self._chars[key]
	
	def __setitem__(self, key, value):
		if isinstance(key, tuple):
			# key is a tuple, set kernpair
			self._kerning[key] = value
		else:
			# set char metrics
			self._chars[key] = value
	
	def __delitem__(self, key):
		if isinstance(key, tuple):
			# key is a tuple, del kernpair
			del self._kerning[key]
		else:
			# del char metrics
			del self._chars[key]
	
	def __repr__(self):
		if hasattr(self, "FullName"):
			return '<AFM object for %s>' % self.FullName
		else:
			return '<AFM object at %x>' % id(self)


def readlines(path):
	f = open(path, 'rb')
	data = f.read()
	f.close()
	# read any text file, regardless whether it's formatted for Mac, Unix or Dos
	sep = ""
	if '\r' in data:
		sep = sep + '\r'	# mac or dos
	if '\n' in data:
		sep = sep + '\n'	# unix or dos
	return data.split(sep)

def writelines(path, lines, sep='\r'):
	f = open(path, 'wb')
	for line in lines:
		f.write(line + sep)
	f.close()
	
	

if __name__ == "__main__":
	import EasyDialogs
	path = EasyDialogs.AskFileForOpen()
	if path:
		afm = AFM(path)
		char = 'A'
		if afm.has_char(char):
			print(afm[char])	# print charnum, width and boundingbox
		pair = ('A', 'V')
		if afm.has_kernpair(pair):
			print(afm[pair])	# print kerning value for pair
		print(afm.Version)	# various other afm entries have become attributes
		print(afm.Weight)
		# afm.comments() returns a list of all Comment lines found in the AFM
		print(afm.comments())
		#print afm.chars()
		#print afm.kernpairs()
		print(afm)
		afm.write(path + ".muck")

