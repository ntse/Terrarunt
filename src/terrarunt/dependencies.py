import importlib.resources
import json
import os

from jsonschema import validate
from jsonschema import ValidationError
from terrarunt.custom_logger import Logger

logger = Logger(__name__)


def get_schema():
    pkg = "terrarunt.resources"
    fname = "dependencies.schema.json"

    schema = importlib.resources.files(pkg).joinpath(fname)
    with schema.open() as f:
        return json.load(f)


class Node:
    def __init__(self, name: str, base_dir: str):
        self.name = name
        self.edges = []
        self.valid_dir = self._verify_dir_exists(base_dir)
        logger.debug(f"{name} was created as a Node object!")

    def _verify_dir_exists(self, base_dir):
        return os.path.isdir(os.path.join(base_dir, self.name))

    def add_edge(self, edge):
        """
        Add an edge (dependency) to the node.

        Args:
            edge (Node): The node to add as a dependency.

        Raises:
            Exception: Raises an exception if a circular reference is detected
        """
        self.edges.append(edge)
        logger.debug(f"Added {edge.name} as edge to node {self.name}")

    def dep_resolve(self, resolved, seen=[]):
        """
        Resolve dependencies recursively starting from this node using a DFS algorithm.

        Args:
            resolved (list): List to store resolved nodes in topological order.
            seen (list, optional): List to track nodes that have been visited to detect cycles. Defaults to [].

        Raises:
            Exception: If a circular reference is detected.
        """
        seen.append(self)
        for edge in self.edges:
            if edge not in resolved:
                if edge in seen:
                    raise Exception(
                        f"Circular reference detected: {self.name} -> {edge.name}",
                    )
                edge.dep_resolve(resolved, seen)
        resolved.append(self)


class Graph:
    def __init__(self, base_dir: str):
        self.nodes = {}
        self.base_dir = base_dir

    def add_node(self, stack_dir: str, dependencies: list):
        """
        Add a node to the graph.

        Args:
            stack_dir (str): Path to the directory which the Node represents.
            dependencies (list): A list of dependencies extracted from the dependencies.json file

        Raises:
            Exception: Raises an exception if a dependency is referenced in the dependencies.json but has no physical directory
        """
        if stack_dir not in self.nodes:
            self.nodes[stack_dir] = Node(stack_dir, self.base_dir)

        node = self.nodes[stack_dir]
        for dep in dependencies:
            if dep not in self.nodes:
                self.nodes[dep] = Node(dep, self.base_dir)
            if not self.nodes[dep].valid_dir:
                raise Exception(
                    f"Unknown dependency detected: non-existent {dep} found in {stack_dir}/dependencies.json",
                )
            node.add_edge(self.nodes[dep])

    def resolve_dependencies(self):
        """
        Resolve dependencies recursively starting from the first node in the nodes attribute.

        Returns:
            list: List of resolved dependencies
        """
        resolved = []
        for node in self.nodes.values():
            node.dep_resolve(resolved)
        return resolved

    def generate_dot_file(self):
        """
        Generate DOT file for creating a visual representation of the graph

        Returns:
            str: DOT-representation of the graph
        """
        try:
            return g.dot()
        except NameError:
            logger.critical(
                "Install gvgen via pip to generate a DOT file of this graph",
            )

    def topological_sort(self):
        """
        Perform topological sorting of nodes in required order of deploy.

        Args:
            nodes (iterable): Iterable of Node objects representing nodes in the graph.

        Returns:
            list: List of Node objects in topologically sorted order.
        """
        sorted_nodes = []
        visited = set()

        def visit(node):
            if node in visited:
                return
            visited.add(node)
            for edge in node.edges:
                visit(edge)
            sorted_nodes.append(node)

        for node in self.nodes.values():
            visit(node)

        return sorted_nodes


def find_stack_directories(start_dir, max_depth=2):
    """
    Find all Terraform stacks specified depth in the directory tree.

    Args:
        start_dir (str): The starting directory to search from.
        max_depth (int, optional): Maximum depth to search in the directory tree. Defaults to 2.

    Returns:
        list: List of file paths to Terraform stack directories found.
    """

    results = []
    for root, _, files in os.walk(start_dir):
        depth = root[len(start_dir):].count(os.sep)
        if depth > max_depth:
            continue
        if "dependencies.json" in files:
            results.append(os.path.join(root, "dependencies.json"))
    return results


def extract_dependencies_from_file(file_path):
    """
    Extract dependencies from a 'dependencies.json' file.

    Args:
        file_path (str): Path to the 'dependencies.json' file.

    Returns:
        list: List of dependencies extracted from the file.
    """
    with open(file_path) as file:
        try:
            data = json.load(file)
            schema = get_schema()
            validate(data, schema)
        except (ValidationError, json.decoder.JSONDecodeError) as e:
            raise ValidationError(
                f"{file_path} failed to validate against the JSON schema",
            ) from e

        return data["dependencies"]["paths"]


def process_stack_files(base_dir):
    """
    Processes stack directories and adds nodes to a graph

    Args:
        base_dir: The base directory containing all of the Terraform scaks

    Returns:
        Graph: A graph object representing all of the stacks found
    """
    graph = Graph(base_dir)
    stack_files = find_stack_directories(base_dir, max_depth=2)
    for file_path in stack_files:
        if file_path.endswith("dependencies.json"):
            stack_dir = (
                f"./{os.path.relpath(os.path.dirname(file_path), base_dir)}"
            )
            dependencies = extract_dependencies_from_file(file_path)
        graph.add_node(stack_dir, dependencies)

    return graph
