from system.plugins.storages.metaartefactdriver import MetaArtefactDriver
from etcdclient import EtcdClient
import json
import logging
from system.helpers.artefactkeygenerator.keygenerator import KeyGeneratorFactory
from system.artefacts.artefacts import ARTEFACT_NO_ARTEFACT

class ArtefactDriver(MetaArtefactDriver):

	def __init__(self, artefact = ARTEFACT_NO_ARTEFACT):
		self.artefact = artefact

	def _generateKey(self, data):
		generator = KeyGeneratorFactory().build(self.artefact)
		if generator == None:
			logging.error("Unable to store %s artefact: key generator not found" % self.artefact)
			return ""

		key = generator.generate(data)
		if key == "":
			logging.error("Unable to store %s artefact: key not generated" % self.artefact)
			return ""

		return key

	def store(self, data):
		"""store artefact"""
		key = self._generateKey(data)
		if key == "":
			return False

		# store the data into etcd
		if EtcdClient().set(key, json.dumps(data)):
			logging.error("Unable to store %s artefact with '%s' key" % (self.artefact, key))
			return False

		# log info
		logging.info("Value for key %s stored" % key)

		return True

	def retrieve(self, key_data):
		"""retrieve artefact"""
		key = self._generateKey(key_data)
		if key == "":
			return False
	
		# get the data from etcd
		ok, value = EtcdClient().get(key)

		if not ok:
			logging.error("Unable to retrieve %s artefact with '%s' key" % (self.artefact, key))
			return ""

		return json.loads(value)

	def storeList(self, dataList):
		"""store list of artefacts"""
		raise NotImplementedError

	def retrieveList(self, key):
		"""retrieve list of artefacts"""
		raise NotImplementedError

