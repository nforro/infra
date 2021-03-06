from infra.system.core.meta.metaartefactkeygenerator import MetaArtefactKeyGenerator
import logging

class GolangProjectPackagesKeyGenerator(MetaArtefactKeyGenerator):

	def generate(self, data, delimiter = ":"):
		# return a list of fields
		keys = []
		for key in ["artefact", "project", "commit"]:
			if key not in data:
				raise ValueError("golang-project-packages: %s key missing" % key)

			keys.append(self.truncateKey(data[key]))

		return keys
