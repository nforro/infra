from infra.system.core.factory.actfactory import ActFactory
from infra.system.artefacts.artefacts import ARTEFACT_GOLANG_PROJECT_PACKAGES
from gofed_lib.importpathsdecomposerbuilder import ImportPathsDecomposerBuilder
from gofed_lib.importpathnormalizer import ImportPathNormalizer
from gofed_lib.importpathparserbuilder import ImportPathParserBuilder
from gofed_lib.snapshot import Snapshot
import logging
import copy

from infra.system.models.graphs.datasets.projectdatasetbuilder import ProjectDatasetBuilder
from infra.system.models.graphs.datasetdependencygraphbuilder import DatasetDependencyGraphBuilder, LEVEL_GOLANG_PACKAGES
from gofed_lib.graphutils import GraphUtils

class ReconstructionError(Exception):
	pass

class SnapshotReconstructor(object):

	def __init__(self):
		# parsers
		self.ipparser = ImportPathParserBuilder().buildWithLocalMapping()

		# acts
		self.go_code_inspection_act = ActFactory().bake("go-code-inspection")
		self.scan_upstream_repository_act = ActFactory().bake("scan-upstream-repository")

		# snapshot
		self._snapshot = Snapshot()

		# dependency space
		self.detected_projects = {}
		self.unscanned_projects = {}
		self.scanned_projects = {}

	def _getCommitTimestamp(self, repository, commit):
		"""Retrieve commit from a repository, returns its commits date

		:param repository: repository
		:type  repository: dict
		:param commit: commit
		:type  commit: hex string
		"""
		data = {
			"repository": repository,
			"commit": commit
		}
		# TODO(jchaloup): catch exception if the commit is not found
		commit_data = self.scan_upstream_repository_act.call(data)
		return commit_data["commits"][commit]["cdate"]

	def _findYoungestCommits(self, commits):
		# sort commits
		commits = map(lambda l: {"c": l, "d": commits[l]["cdate"]}, commits)
		commits = sorted(commits, key = lambda commit: commit["d"])

		return commits[-1]

	def _findClosestCommit(self, repository, timestamp):
		"""Get the oldest commits from the repository that is at most old as timestamp.

		:param repository: repository
		:type  repository: dict
		:param timestamp: commit timestamp
		:type  timestamp: integer
		"""
		# TODO(jchaloup): search for commits only on master branch!!!
		# other branches can be in inconsystem state with experimental features
		# and get picked unintensionaly
		data = {
			"repository": repository,
			"end_timestamp": timestamp
		}

		DAY = 3600*24
		# try the last day, week, last month, last year
		for delta in [1, 7, 30, 365]:
			data["start_timestamp"] = timestamp - delta*DAY
			rdata = self.scan_upstream_repository_act.call(data)
			if rdata["commits"] != {}:
				return self._findYoungestCommits(rdata["commits"])

		# unbound start_timestamp
		del data["start_timestamp"]
		rdata = self.scan_upstream_repository_act.call(data)
		if rdata["commits"] != {}:
			return self._findYoungestCommits(rdata["commits"])

		# no commit foud => raise exception
		raise KeyError("Commit not found")

	def _detectNextDependencies(self, dependencies, ipprefix, commit_timestamp):
		dependencies = list(set(dependencies))
		# normalize paths
		normalizer = ImportPathNormalizer()
		dependencies = map(lambda l: normalizer.normalize(l), dependencies)

		decomposer = ImportPathsDecomposerBuilder().buildLocalDecomposer()
		decomposer.decompose(dependencies)
		prefix_classes = decomposer.getClasses()

		next_projects = {}

		for prefix in prefix_classes:
			# filter out Native prefix
			if prefix == "Native":
				continue

			# filter out project's import path prefix
			if prefix == ipprefix:
				continue

			logging.warning("Processing %s ..." % prefix)

			# for each imported path get a list of commits in a given interval
			try:
				self.ipparser.parse(prefix)
				# ipprefix already covered?
				if self.ipparser.getImportPathPrefix() in self.detected_projects:
					# ip covered in the prefix class?
					not_covered = []
					for ip in prefix_classes[prefix]:
						if ip not in self.detected_projects[prefix]:
							not_covered.append(ip)

					if not_covered == []:
						logging.warning("Prefix %s already covered" % prefix)
						continue

						logging.warning("Some paths '%s' not yet covered in '%s' prefix" % (str(not_covered), prefix))
					# scan only ips not yet covered
					prefix_classes[prefix] = not_covered

				provider = self.ipparser.getProviderSignature()
				provider_prefix = self.ipparser.getProviderPrefix()
			except ValueError as e:
				raise ReconstructionError("Prefix provider error: %s" % e)

			try:
				closest_commit = self._findClosestCommit(provider, commit_timestamp)
			except KeyError as e:
				raise ReconstructionError("Closest commit to %s timestamp for %s not found" % (commit_timestamp, provider_prefix))

			# update packages to scan
			next_projects[prefix] = {
				"ipprefix": prefix,
				"paths": map(lambda l: str(l), prefix_classes[prefix]),
				"provider": provider,
				"commit": closest_commit["c"],
				#"timestamp": closest_commit["d"],
				"provider_prefix": provider_prefix
			}

		return next_projects

	def _detectDirectDependencies(self, repository, commit, ipprefix, commit_timestamp, mains, tests):
		data = {
			"type": "upstream_source_code",
			"project": "github.com/coreos/etcd",
			"commit": commit,
			"ipprefix": ipprefix,
			"directories_to_skip": []
		}

		packages_artefact = self.go_code_inspection_act.call(data)

		# collect dependencies
		direct_dependencies = []
		for package in packages_artefact["data"]["dependencies"]:
			direct_dependencies = direct_dependencies + map(lambda l: l["name"], package["dependencies"])

		if mains != []:
			paths = {}
			for path in packages_artefact["data"]["main"]:
				paths[path["filename"]] = path["dependencies"]

			for main in mains:
				if main not in paths:
					raise ReconstructionError("Main package file %s not found" % main)

				direct_dependencies = direct_dependencies + paths[main]

		if tests:
			for dependencies in map(lambda l: l["dependencies"], packages_artefact["data"]["tests"]):
				direct_dependencies = direct_dependencies + dependencies

		# remove duplicates
		direct_dependencies = list(set(direct_dependencies))

		next_projects = self._detectNextDependencies(direct_dependencies, ipprefix, commit_timestamp)

		# update detected projects
		for project in next_projects:
			self.detected_projects[project] = next_projects[project]["paths"]

		# update packages to scan
		for prefix in next_projects:
			if prefix in self.unscanned_projects:
				continue

			self.unscanned_projects[prefix] = copy.deepcopy(next_projects[prefix])
			self.scanned_projects[prefix] = copy.deepcopy(next_projects[prefix])

	def _detectIndirectDependencies(self, ipprefix, commit_timestamp):
		nodes = []
		next_projects = {}
		for prefix in self.unscanned_projects:
			# get dataset
			dataset = ProjectDatasetBuilder(
				self.unscanned_projects[prefix]["provider_prefix"],
				self.unscanned_projects[prefix]["commit"]
			).build()

			# construct dependency graph from the dataset
			graph = DatasetDependencyGraphBuilder().build(dataset, LEVEL_GOLANG_PACKAGES)

			# get the subgraph of evolved dependency's packages
			subgraph = GraphUtils.truncateGraph(graph, self.unscanned_projects[prefix]["paths"])

			# get dependencies from the subgraph
			package_nodes = filter(lambda l: l.startswith(self.unscanned_projects[prefix]["ipprefix"]), subgraph.nodes())
			label_edges = dataset.getLabelEdges()
			for node in package_nodes:
				nodes = nodes + label_edges[node]

		nodes = list(set(nodes))

		next_projects = self._detectNextDependencies(nodes, ipprefix, commit_timestamp)
		if next_projects == {}:
			return False

		# update packages to scan
		one_at_least = False
		self.unscanned_projects = {}

		for prefix in next_projects:
			# prefix already covered? Just extend the current coverage
			if prefix in self.detected_projects:
				for ip in next_projects[prefix]["paths"]:
					if str(ip) not in self.detected_projects[prefix]:
						self.detected_projects[prefix].append(ip)
						self.scanned_projects[prefix]["paths"].append(ip)
				continue

			one_at_least = True
			self.unscanned_projects[prefix] = copy.deepcopy(next_projects[prefix])
			self.scanned_projects[prefix] = copy.deepcopy(next_projects[prefix])
			self.detected_projects[prefix] = copy.deepcopy(next_projects[prefix]["paths"])

		return one_at_least

	def reconstruct(self, repository, commit, ipprefix, mains = [], tests = False):
		"""Reconstruct snapshot
		:param repository: project repository
		:type  repository: dict
		:param commit: repository commit
		:type  commit: string
		:param ipprefix: import path prefix
		:type  ipprefix: string
		:param mains: list of main packages with root path to go file to cover, implicitly no main package, just devel
		:type  mains: [string]
		:param tests: cover unit tests as well, default is False
		:type  tests: boolean
		"""

		# clear snapshot
		self._snapshot.clear()

		# get commit date of project's commit
		commit_timestamp = self._getCommitTimestamp(repository, commit)
		# get direct dependencies
		logging.info("=============DIRECT==============")
		self._detectDirectDependencies(repository, commit, ipprefix, commit_timestamp, mains, tests)

		# scan detected dependencies
		logging.info("=============UNDIRECT==============")
		while self._detectIndirectDependencies(ipprefix, commit_timestamp):
			logging.info("=============UNDIRECT==============")

		# create snapshot
		for prefix in self.scanned_projects:
			for ip in sorted(self.scanned_projects[prefix]["paths"]):
				self._snapshot.addPackage(ip, self.scanned_projects[prefix]["commit"])

		return self

	def snapshot(self):
		return self._snapshot

