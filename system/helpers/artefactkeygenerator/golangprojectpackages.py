from system.core.meta.metaartefactkeygenerator import MetaArtefactKeyGenerator
import logging

class GolangProjectPackagesKeyGenerator(MetaArtefactKeyGenerator):

	def generate(self, data, delimiter = ":"):
		# return a list of fields
		keys = []
		for key in ["artefact", "project", "commit"]:
			if key not in data:
				logging.error("golang-project-packages: %s key missing" % key)
				return ""

			keys.append(data[key])

		return delimiter.join(keys)
