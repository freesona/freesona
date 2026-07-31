# tests/test_math.py: Python module.
from cogs.tools.math import MathCog, generate_plot, is_safe_expression
import sys
import unittest
from pathlib import Path

# Add workspace directory to path to allow importing cogs
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


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
            "expand((x + y)**2)",
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
            "compile('1', '', 'eval')",
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
            ("pi", "3.141592654"),
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
            "__import__('os').system('whoami')",
        ]
        for query in ignored_cases:
            with self.subTest(query=query):
                self.assertIsNone(self.cog.solve_locally(query))

    def test_generate_plot_explicit(self):
        import io

        # Test generating plot for explicit functions (regression)
        for expr in [
            "x**2",
            "sin(x)",
            "x**3 - 2*x + 1",
            "y = x**2",
            "f(x)=x**2",
        ]:
            with self.subTest(expr=expr):
                buf = generate_plot(expr)
                self.assertIsInstance(buf, io.BytesIO)
                png_data = buf.getvalue()
                self.assertTrue(png_data.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_generate_plot_implicit(self):
        import io

        # Test generating plot for implicit functions
        for expr in [
            "x**2 + y**2 = 1",  # circle
            "(x**2 + y**2 - 1)**3 - x**2 * y**3 = 0",  # heart curve
        ]:
            with self.subTest(expr=expr):
                buf = generate_plot(expr)
                self.assertIsInstance(buf, io.BytesIO)
                png_data = buf.getvalue()
                self.assertTrue(png_data.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_generate_plot_parametric(self):
        import io

        # Test generating plot for parametric equations
        for expr in [
            "x = cos(t), y = sin(t)",  # circle
            # heart
            "x = 16*sin(t)**3, y = 13*cos(t) - 5*cos(2*t) - 2*cos(3*t) - cos(4*t)",
        ]:
            with self.subTest(expr=expr):
                buf = generate_plot(expr)
                self.assertIsInstance(buf, io.BytesIO)
                png_data = buf.getvalue()
                self.assertTrue(png_data.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_format_wolfram_text(self):
        # Test basic filtering
        self.assertEqual(
            self.cog.format_wolfram_text(
                "Input interpretation: 2+2\nResult:\n4"
            ),
            "4",
        )
        # Test table formatting (piped output)
        self.assertEqual(
            self.cog.format_wolfram_text("Name | Value\nApple | Red"),
            "**Name ** | Value\n**Apple ** | Red",
        )
        # Test stripping links and Wolfram ads
        self.assertEqual(
            self.cog.format_wolfram_text(
                "Wolfram Language code: foo\nResult:\n4\nplot: https://example.com/plot.png"
            ),
            "4",
        )
        self.assertEqual(self.cog.format_wolfram_text(""), "No result found.")

    def test_regression_expressions_previously_failing(self):
        """Test that expressions which previously failed the is_safe_expression check now work for plotting."""
        # These expressions used to fail with "Unsafe characters or expressions detected"
        # They should now generate valid plots
        import io

        for expr in [
            "f(x)=x**2",  # function notation
            "(x^2 + y^2 - 1)^3 - x^2*y^3 = 0",  # heart curve (with ^)
            # parametric heart
            "x = 16*sin(t)^3, y = 13*cos(t) - 5*cos(2*t) - 2*cos(3*t) - cos(4*t)",
        ]:
            with self.subTest(expr=expr):
                buf = generate_plot(expr)
                self.assertIsInstance(buf, io.BytesIO)
                png_data = buf.getvalue()
                self.assertTrue(png_data.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_solve_locally_still_secure(self):
        """Ensure solve_locally still rejects dangerous expressions (security regression test)."""
        dangerous = [
            "__import__('os').system('whoami')",
            "eval('2+2')",
            "lambda x: x",
            "open('file.txt')",
            "__builtins__",
        ]
        for expr in dangerous:
            with self.subTest(expr=expr):
                result = self.cog.solve_locally(expr)
                self.assertIsNone(
                    result, f"solve_locally should reject: {expr}"
                )


if __name__ == "__main__":
    unittest.main()
