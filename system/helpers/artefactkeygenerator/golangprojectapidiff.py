from infra.system.core.meta.metaartefactkeygenerator import MetaArtefactKeyGenerator
import logging

class GolangProjectApiDiffKeyGenerator(MetaArtefactKeyGenerator):

	def generate(self, data, delimiter = ":"):
		# return a list of fields
		keys = []
		for key in ["artefact", "project", "commit1", "commit2"]:
			if key not in data:
				raise ValueError("golang-project-api-diff: %s key missing" % key)

			keys.append(self.truncateKey(data[key]))

		return keys
