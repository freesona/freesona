import unittest
import sys
from pathlib import Path

# Add workspace directory to path to allow importing cogs
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cogs.tools.math import is_safe_expression, MathCog

class MockBot:
    pass

class MathCogTests(unittest.TestCase):
    def setUp(self):
        self.cog = MathCog(MockBot())

    def test_is_safe_expression_valid(self):
        valid_expressions = [
            "2 + 2",
            "x + x",
            "sin(x) + cos(y)",
            "solve(x**2 - 4, x)",
            "integrate(x**2, (x, 0, 1))",
            "pi * r**2",
            "log(10) / exp(1)",
            "x",
            "1/2",
            "cos(0)",
            "expand((x + y)**2)"
        ]
        for expr in valid_expressions:
            with self.subTest(expr=expr):
                self.assertTrue(is_safe_expression(expr))

    def test_is_safe_expression_invalid_rce(self):
        invalid_expressions = [
            "__import__('os').system('whoami')",
            "os.system('whoami')",
            "import os",
            "eval('2+2')",
            "x.system('whoami')",
            "getattr(x, 'system')",
            "x + # comment",
            "2 + 2; import sys",
            "lambda x: x",
            "[x for x in [1, 2, 3]]",
            "open('file.txt')",
            "__builtins__",
            "compile('1', '', 'eval')"
        ]
        for expr in invalid_expressions:
            with self.subTest(expr=expr):
                self.assertFalse(is_safe_expression(expr))

    def test_solve_locally_successful(self):
        # Math problems that should be solved locally
        test_cases = [
            ("2 + 2", "4"),
            ("x + x", "2*x"),
            ("solve(x**2 - 1, x)", "[-1, 1]"),
            ("cos(0)", "1"),
            ("1/2", "0.5"),
            ("pi", "3.141592654")
        ]
        for query, expected in test_cases:
            with self.subTest(query=query):
                self.assertEqual(self.cog.solve_locally(query), expected)

    def test_solve_locally_ignored(self):
        # Queries that should return None so they fall back to Wolfram Alpha
        ignored_cases = [
            "weather",
            "hello",
            "x",
            "x + y",
            "sin(x)",
            "__import__('os').system('whoami')"
        ]
        for query in ignored_cases:
            with self.subTest(query=query):
                self.assertIsNone(self.cog.solve_locally(query))

    def test_generate_plot(self):
        from cogs.tools.math import generate_plot
        import io
        # Test generating plot for a simple expression
        buf = generate_plot("x**2")
        self.assertIsInstance(buf, io.BytesIO)
        # Ensure the bytes returned are actually a PNG image
        png_data = buf.getvalue()
        self.assertTrue(png_data.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_format_wolfram_text(self):
        # Test basic filtering
        self.assertEqual(self.cog.format_wolfram_text("Input interpretation: 2+2\nResult:\n4"), "4")
        # Test table formatting (piped output)
        self.assertEqual(self.cog.format_wolfram_text("Name | Value\nApple | Red"), "**Name ** | Value\n**Apple ** | Red")
        # Test stripping links and Wolfram ads
        self.assertEqual(
            self.cog.format_wolfram_text("Wolfram Language code: foo\nResult:\n4\nplot: https://example.com/plot.png"),
            "4"
        )
        self.assertEqual(self.cog.format_wolfram_text(""), "No result found.")


if __name__ == "__main__":
    unittest.main()
