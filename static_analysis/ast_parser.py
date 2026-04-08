import ast


class PythonASTAnalyzer(ast.NodeVisitor):

    def __init__(self):
        self.functions = 0
        self.classes = 0
        self.imports = set()
        self.loops = 0
        self.conditionals = 0
        self.function_lengths = []

    def visit_FunctionDef(self, node):
        self.functions += 1

        start = node.lineno
        end = getattr(node, "end_lineno", node.lineno)

        self.function_lengths.append(end - start)

        self.generic_visit(node)

    def visit_ClassDef(self, node):
        self.classes += 1
        self.generic_visit(node)

    def visit_Import(self, node):
        for name in node.names:
            self.imports.add(name.name)

    def visit_ImportFrom(self, node):
        if node.module:
            self.imports.add(node.module)

    def visit_For(self, node):
        self.loops += 1
        self.generic_visit(node)

    def visit_While(self, node):
        self.loops += 1
        self.generic_visit(node)

    def visit_If(self, node):
        self.conditionals += 1
        self.generic_visit(node)


def analyze_python_file(file_path):
    """
    Safely analyze a Python file using AST.
    """

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()

        tree = ast.parse(source)

        analyzer = PythonASTAnalyzer()
        analyzer.visit(tree)

        return {
            "functions": analyzer.functions,
            "classes": analyzer.classes,
            "imports": list(analyzer.imports),
            "loops": analyzer.loops,
            "conditionals": analyzer.conditionals,
            "function_lengths": analyzer.function_lengths,
        }

    except Exception:
        # if parsing fails we return None
        return None