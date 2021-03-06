from infra.system.helpers.schema_validator import SchemaValidator

class MetaProcessor:
	"""
	Abstract class that each analysis, extractor
	and other kind must re-implement.

	In general, processor can have flags whose value
	depends on data. E.g. directories to skip (Godeps, vendor).
	Those flags are a part of data to process.

	At the same time each processor have default configuration.
	E.g. log directory, verbose mode, etc.
	Configuration is not part of data.

	https://github.com/gofed/infra/issues/8
	"""

	def __init__(self, schema, ref_schema_directory = ""):
		self.schema = schema
		if ref_schema_directory != "":
			self.validator = SchemaValidator(ref_schema_directory)
		else:
			self.validator = SchemaValidator()

	def setData(self, data):
		"""Validation and data pre-processing"""
		raise NotImplementedError

	def getData(self):
		"""Validation and data post-processing"""
		raise NotImplementedError

	def execute(self):
		"""Impementation of concrete data processor"""
		raise NotImplementedError

	def _validateInput(self, data):
		return self.validator.validateFromFile(self.schema, data)

