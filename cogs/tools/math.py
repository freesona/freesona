# cogs/tools/math.py: Local, Wolfram Alpha, and Visualization solution

import ast
import asyncio
import io
import logging
import os
import re
from typing import Any, cast
from urllib.parse import quote

import aiohttp
import discord
import numpy as np
import sympy
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

# Force SymPy to use SymEngine as the primary backend BEFORE importing sympy
os.environ["SYMPY_BACKEND"] = "symengine"


logger = logging.getLogger(__name__)

try:
    import importlib.util

    if importlib.util.find_spec("symengine") is not None:
        import symengine  # noqa: F401

        logger.info("SymEngine successfully loaded as the symbolic backend.")
    else:
        logger.warning("SymEngine not found. Falling back to default SymPy.")
except ImportError:
    logger.warning("SymEngine not found. Falling back to default SymPy.")
except (OSError, ModuleNotFoundError, AttributeError):
    logger.warning("SymEngine not available — falling back to pure Python SymPy.")


try:
    from matplotlib.figure import Figure
except ImportError:
    Figure = None


load_dotenv()


def _sympify(expr: str, *, evaluate: bool) -> Any:
    """Call SymPy's parser with the legacy evaluate flag through a safe cast.

    This preserves the original parse/evaluate split used by the math helpers
    while avoiding the static-analysis signature mismatch reported for the
    direct `sympy.sympify(..., evaluate=False)` call pattern.
    """
    return cast(Any, sympy.sympify)(expr, evaluate=evaluate)


WOLFRAM_SHORT_APPID = os.getenv("WOLFRAM_APPID_SHORT")
WOLFRAM_LLM_APPID = os.getenv("WOLFRAM_APPID_LLM")

SAFE_FUNCTIONS = {
    # Trigonometric
    "sin",
    "cos",
    "tan",
    "cot",
    "sec",
    "csc",
    "asin",
    "acos",
    "atan",
    "acot",
    "asec",
    "acsc",
    "sinh",
    "cosh",
    "tanh",
    "coth",
    "sech",
    "csch",
    "asinh",
    "acosh",
    "atanh",
    "acoth",
    "asech",
    "acsch",
    # Algebraic & Arithmetic
    "sqrt",
    "cbrt",
    "exp",
    "log",
    "ln",
    "log10",
    "log2",
    "abs",
    "factorial",
    "gamma",
    "floor",
    "ceiling",
    "mod",
    "sign",
    "max",
    "min",
    "sum",
    "prod",
    "pow",
    "power",
    "root",
    # Calculus
    "limit",
    "diff",
    "integrate",
    "solve",
    "expand",
    "simplify",
    "series",
    "dsolve",
    "nsolve",
    # Constants
    "pi",
    "E",
    "e",
    "I",
    "oo",
    "Infinity",
    "nan",
    "S",
    "EulerGamma",
    "Catalan",
    "GoldenRatio",
    # Special functions
    "summation",
    "product",
    "N",
    "evalf",
    "n",
    "zeta",
    "polygamma",
    "digamma",
    "trigamma",
    "besselj",
    "bessely",
    "besseli",
    "besselk",
    "airyai",
    "airybi",
    "legendre",
    "chebyshevt",
    "chebyshevu",
    "hermite",
    "laguerre",
    "jacobi",
    "erf",
    "erfc",
    "erfi",
    "erfinv",
    "erfcinv",
    "fresnels",
    "fresnelc",
    "elliptic_e",
    "elliptic_f",
    "elliptic_k",
    "elliptic_pi",
    # Hyperbolic
    # Matrix/Vector (basic)
    "Matrix",
    "det",
    "trace",
    "rank",
    "eigenvals",
    "eigenvects",
    # Rounding
    "round",
    "trunc",
    "frac",
    # Sympy core symbols and functions (added for plotting and solve_locally)
    "Symbol",
    "symbols",
    "Function",
    "Eq",
    "Ne",
    "Lt",
    "Le",
    "Gt",
    "Ge",
    "Abs",
    "conjugate",
    "re",
    "im",
    "arg",
    "factorial2",
    "rf",
    "ff",
    "binomial",
    "multinomial",
    "catalan",
    "euler",
    "harmonic",
    "stirling",
    "bernoulli",
    "bell",
    "fibonacci",
    "lucas",
    "partitions",
    "fourier_transform",
    "laplace_transform",
    "inverse_fourier_transform",
    "inverse_laplace_transform",
    "eye",
    "zeros",
    "ones",
    "diag",
    "BlockMatrix",
    "MutableMatrix",
    "ImmutableMatrix",
    # Additional constants
    "NaN",
}


def check_ast_safe(node) -> bool:
    allowed_nodes = (
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.Name,
        ast.Call,
        ast.Tuple,
        ast.List,
        ast.keyword,
        ast.Subscript,
        ast.Slice,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.Pow,
        ast.Mod,
        ast.FloorDiv,
        ast.UAdd,
        ast.USub,
        ast.Load,
        ast.Store,
        ast.Del,
        ast.Compare,
        ast.Eq,
        ast.NotEq,
        ast.Lt,
        ast.LtE,
        ast.Gt,
        ast.GtE,
        ast.BoolOp,
        ast.And,
        ast.Or,
        ast.Not,
    )

    if not isinstance(node, allowed_nodes):
        return isinstance(node, ast.Constant) and (
            isinstance(node.value, (int, float, complex, bool)) or node.value is None
        )

    if isinstance(node, ast.Name):
        return not (
            node.id.startswith("__")
            or node.id
            in {
                "eval",
                "exec",
                "open",
                "__import__",
                "print",
                "getattr",
                "setattr",
                "delattr",
                "compile",
                "globals",
                "locals",
                "input",
                "exit",
                "quit",
                "help",
                "copyright",
                "credits",
                "license",
            }
        )

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            return False
        if node.func.id not in SAFE_FUNCTIONS:
            return False

    for child in ast.iter_child_nodes(node):
        if not check_ast_safe(child):
            return False
    return True


def is_safe_expression(query: str) -> bool:
    try:
        # Check that there are no control characters or comments
        if "#" in query or ";" in query:
            return False
        tree = ast.parse(query, mode="eval")
        return check_ast_safe(tree)
    except (SyntaxError, ValueError, RecursionError):
        return False


def _minimal_png_placeholder() -> io.BytesIO:
    buf = io.BytesIO()
    buf.write(
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc`\x00\x00\x00\x02\x00\x01"
        b"\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    buf.seek(0)
    return buf


def _generate_explicit_plot(func_str: str) -> io.BytesIO:
    """Generate plot for explicit functions y = f(x)."""
    if Figure is None:
        return _minimal_png_placeholder()

    clean_func = func_str.replace("^", "**")

    # Handle function notation f(x) = expr, y = expr, x = expr -> extract expr
    if "=" in clean_func and "==" not in clean_func:
        lhs, rhs = clean_func.split("=", 1)
        lhs = lhs.strip()
        rhs = rhs.strip()
        # Check if LHS looks like f(x), g(x), y, or x (non-parametric)
        if ("(" in lhs and ")" in lhs and lhs.endswith(")")) or lhs.lower() in (
            "y",
            "x",
        ):
            # Function notation or simple y=expr or x=expr - use RHS
            clean_func = rhs

    x_symbol = sympy.Symbol("x")
    expr = sympy.sympify(clean_func, evaluate=True)  # type: ignore[call-arg]
    y_func = sympy.lambdify(x_symbol, expr, "numpy")

    x = np.linspace(-10, 10, 400)
    with np.errstate(divide="ignore", invalid="ignore"):
        y = y_func(x)

    if not isinstance(y, np.ndarray):
        y = np.array(y)

    if y.shape == ():
        y = np.full_like(x, y, dtype=float)

    if np.iscomplexobj(y):
        y = np.real(y)

    fig = Figure(figsize=(6, 4))
    ax = fig.subplots()
    ax.plot(x, y)
    ax.set_title(f"Plot of {func_str}")
    ax.grid(True)

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    buf.seek(0)
    return buf


def _generate_implicit_plot(func_str: str) -> io.BytesIO:
    """Generate plot for implicit functions f(x, y) = 0 or
    f(x, y) = g(x, y)."""
    if Figure is None:
        return _minimal_png_placeholder()

    clean_func = func_str.replace("^", "**")

    # Parse the equation - handle f(x)=expr, f(x,y)=expr, etc.
    if "=" in clean_func and "==" not in clean_func:
        lhs_str, rhs_str = clean_func.split("=", 1)
        lhs = lhs_str.strip()
        rhs = rhs_str.strip()

        # Check if LHS is a function call like f(x), f(x,y), etc.
        # If so, we need to treat it as an implicit equation
        try:
            lhs_expr = _sympify(lhs, evaluate=False)
            rhs_expr = _sympify(rhs, evaluate=False)
            expr = sympy.Eq(lhs_expr, rhs_expr)
        except (SyntaxError, ValueError, TypeError, sympy.SympifyError):
            # If parsing fails, try whole expression
            expr = _sympify(clean_func, evaluate=False)
    else:
        expr = _sympify(clean_func, evaluate=False)

    # Get free symbols to determine variables
    x_sym = sympy.Symbol("x")
    y_sym = sympy.Symbol("y")

    # Use matplotlib to plot implicit function by creating a contour plot
    try:
        # Convert expression to a form suitable for contour plotting
        # For Eq(lhs, rhs), we plot lhs - rhs = 0
        if isinstance(expr, sympy.Eq):
            implicit_expr = expr.lhs - expr.rhs  # type: ignore
        else:
            implicit_expr = expr

        # Lambdify for numerical evaluation
        f = sympy.lambdify((x_sym, y_sym), implicit_expr, "numpy")

        # Create grid
        x = np.linspace(-10, 10, 400)
        y = np.linspace(-10, 10, 400)
        x_grid, y_grid = np.meshgrid(x, y)

        with np.errstate(divide="ignore", invalid="ignore"):
            z_grid = f(x_grid, y_grid)

        # Handle complex values
        if np.iscomplexobj(z_grid):
            z_grid = np.real(z_grid)

        # Replace inf/nan with large values
        z_grid = np.nan_to_num(z_grid, nan=1e10, posinf=1e10, neginf=-1e10)

        # Create contour plot at level 0
        fig = Figure(figsize=(6, 4))
        ax = fig.subplots()
        ax.contour(x_grid, y_grid, z_grid, levels=[0], colors="blue", linewidths=2)
        ax.set_title(f"Plot of {func_str}")
        ax.grid(True)
        ax.set_xlim(-10, 10)
        ax.set_ylim(-10, 10)
        ax.set_aspect("equal", adjustable="box")

        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        buf.seek(0)
        return buf

    except (
        ValueError,
        TypeError,
        sympy.SympifyError,
        np.linalg.LinAlgError,
        ZeroDivisionError,
    ) as e:
        logger.warning(f"Implicit plot failed, falling back to placeholder: {e}")
        return _minimal_png_placeholder()


def _generate_parametric_plot(func_str: str) -> io.BytesIO:
    """Generate plot for parametric equations x = f(t), y = g(t)."""
    if Figure is None:
        return _minimal_png_placeholder()

    clean_func = func_str.replace("^", "**")

    # Parse parametric equations: x = ..., y = ...
    parts = [p.strip() for p in clean_func.split(",")]
    x_expr = None
    y_expr = None
    t_sym = sympy.Symbol("t")

    for part in parts:
        if "=" in part:
            lhs, rhs = part.split("=", 1)
            lhs = lhs.strip()
            rhs = rhs.strip()
            if lhs in ("x", "X"):
                try:
                    x_expr = _sympify(rhs, evaluate=False)
                except (
                    SyntaxError,
                    ValueError,
                    TypeError,
                    sympy.SympifyError,
                ):
                    pass
            elif lhs in ("y", "Y"):
                try:
                    y_expr = _sympify(rhs, evaluate=False)
                except (
                    SyntaxError,
                    ValueError,
                    TypeError,
                    sympy.SympifyError,
                ):
                    pass

    if x_expr is None or y_expr is None:
        return _minimal_png_placeholder()

    try:
        # Lambdify for numerical evaluation
        x_func = sympy.lambdify(t_sym, x_expr, "numpy")
        y_func = sympy.lambdify(t_sym, y_expr, "numpy")

        # Create parameter range
        t = np.linspace(-10, 10, 1000)

        with np.errstate(divide="ignore", invalid="ignore"):
            x_vals = x_func(t)
            y_vals = y_func(t)

        # Handle complex values
        if np.iscomplexobj(x_vals):
            x_vals = np.real(x_vals)
        if np.iscomplexobj(y_vals):
            y_vals = np.real(y_vals)

        # Replace inf/nan
        x_vals = np.nan_to_num(x_vals, nan=0, posinf=0, neginf=0)
        y_vals = np.nan_to_num(y_vals, nan=0, posinf=0, neginf=0)

        fig = Figure(figsize=(6, 4))
        ax = fig.subplots()
        ax.plot(x_vals, y_vals, "b-", linewidth=1.5)
        ax.set_title(f"Plot of {func_str}")
        ax.grid(True)
        ax.set_aspect("equal", adjustable="box")

        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        buf.seek(0)
        return buf

    except (
        ValueError,
        TypeError,
        np.linalg.LinAlgError,
        ZeroDivisionError,
        OverflowError,
    ) as e:
        logger.warning(f"Parametric plot failed, falling back to placeholder: {e}")
        return _minimal_png_placeholder()


def generate_plot(func_str: str) -> io.BytesIO:
    """Generate plot for various types of mathematical expressions."""
    if Figure is None:
        return _minimal_png_placeholder()

    clean_func = func_str.replace("^", "**")

    # Detect plot type
    has_equals = "=" in clean_func and "==" not in clean_func
    has_parametric = has_equals and any(
        c in clean_func.lower() for c in ["t", "θ", "theta"]
    )

    # Check for function notation like f(x)=expr, g(x)=expr, y=expr -> treat
    # as explicit
    is_function_notation = False
    if has_equals:
        lhs = clean_func.split("=", 1)[0].strip()
        # Pattern: f(x), g(x), y, etc.
        if lhs.endswith(")") and "(" in lhs:
            # f(x), g(x), etc.
            is_function_notation = True
        elif lhs.lower() in ("y", "x"):
            # y = expr or x = expr (but x = is usually parametric, so check for
            # t)
            is_function_notation = True

    try:
        if has_parametric and clean_func.count("=") >= 2:
            # Parametric: x = f(t), y = g(t)
            return _generate_parametric_plot(clean_func)
        elif has_equals and not is_function_notation:
            # Implicit: f(x, y) = 0 or f(x, y) = g(x, y)
            return _generate_implicit_plot(clean_func)
        else:
            # Explicit: y = f(x) or function notation f(x)=expr
            return _generate_explicit_plot(clean_func)
    except Exception as e:
        logger.error(f"Plot generation failed: {e}")
        raise


class MathCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def solve_locally(self, query: str) -> str | None:
        try:
            clean_query = query.replace("^", "**")

            # Handle function definitions/equations (e.g., f(x)=x^2, y=mx+b)
            # Check for single = but not comparison operators
            if (
                "=" in clean_query
                and "==" not in clean_query
                and "!=" not in clean_query
                and "<=" not in clean_query
                and ">=" not in clean_query
            ):
                try:
                    # Try to parse as sympy equation and solve
                    lhs_str, rhs_str = clean_query.split("=", 1)
                    lhs = _sympify(lhs_str.strip(), evaluate=False)
                    rhs = _sympify(rhs_str.strip(), evaluate=False)
                    equation = sympy.Eq(lhs, rhs)

                    # Find free symbols to solve for
                    free_symbols = equation.free_symbols
                    if free_symbols:
                        # Solve for the first free symbol (typically x)
                        solutions = sympy.solve(
                            equation, next(iter(free_symbols)), dict=True
                        )
                        if solutions:
                            # Format solutions nicely
                            result_parts = []
                            for sol in solutions:
                                for var, val in sol.items():
                                    result_parts.append(f"{var} = {val}")
                            return "; ".join(result_parts)
                except (
                    SyntaxError,
                    ValueError,
                    TypeError,
                    sympy.SympifyError,
                ):
                    # If equation parsing fails, fall through to normal
                    # evaluation
                    pass

            # 1. Critical safety validation
            if not is_safe_expression(clean_query):
                logger.debug(
                    f"Expression not valid for local eval (will try Wolfram): {query}"
                )
                return None

            parsed_expr = _sympify(clean_query, evaluate=False)
            result = _sympify(clean_query, evaluate=True)

            # If the result is a SymPy Symbol, it's just a variable name
            # (unsimplified/unsolved)
            if getattr(result, "is_Symbol", False):
                return None

            is_sympy_obj = hasattr(result, "is_number")
            is_different = result != parsed_expr
            is_number = is_sympy_obj and result.is_number
            is_container = isinstance(result, (list, tuple, dict, set))

            if is_number and not isinstance(result, (list, tuple, dict, set)):
                if not getattr(result, "is_Integer", False):
                    evalf_fn = getattr(result, "evalf", None)
                    if evalf_fn:
                        raw_float = str(evalf_fn(10))
                        if "." in raw_float:
                            return raw_float.rstrip("0").rstrip(".")
                        return raw_float
                return str(result)

            if is_different or is_container:
                return str(result)

            return None
        except (
            SyntaxError,
            ValueError,
            TypeError,
            sympy.SympifyError,
            RecursionError,
        ) as e:
            logger.debug(f"Local solve failed: {e}")
            return None

    async def plot_function(self, ctx, func_str: str):
        # 1. Clean input
        func_str_clean = func_str.strip()
        if not func_str_clean:
            await ctx.send(
                "Please provide a mathematical function of `x` to plot "
                "(e.g., `x**2` or `sin(x)`)."
            )
            return

        # 2. Offload blocking matplotlib rendering to a separate thread
        try:
            buf = await asyncio.to_thread(generate_plot, func_str_clean)
        except (RuntimeError, ValueError, TypeError, MemoryError) as e:
            await ctx.send(f"Error plotting function: {e}")
            return

        file = discord.File(buf, filename="plot.png")
        embed = discord.Embed(title=f"Plot of {func_str_clean}", color=0xDA5B40)
        embed.set_image(url="attachment://plot.png")
        embed.set_footer(text=f"Query: plot {func_str_clean}")

        await ctx.send(embed=embed, file=file)

    def format_wolfram_text(self, text: str) -> str:
        if not text:
            return "No result found."
        text = re.sub(r"(?i)Wolfram Language code:.*", "", text)
        text = re.sub(r"(?i)Wolfram\s*\|\s*Alpha website result.*", "", text)
        text = re.sub(r"(?i)Input interpretation:.*?\n", "", text)
        text = re.sub(r"(?i)Result:\s*\n*", "", text)
        text = re.sub(r"(?i)(plot|image|url):\s*https?://\S+", "", text)
        text = re.sub(r"https?://\S+", "", text)
        text = re.sub(r"(?m)^([^:\n|]+)\s*\|\s*([^\n]+)", r"**\1** | \2", text)
        text = re.sub(r"\n\s*\n", "\n", text)
        return text.strip()

    def create_embed(self, title: str, content: str, query: str) -> discord.Embed:
        formatted_content = self.format_wolfram_text(content)
        embed = discord.Embed(
            title=title,
            description=formatted_content[:4096] or "No result found.",
            color=0xDA5B40,
        )
        clean_math = formatted_content.replace("**", "").replace("`", "").strip()

        if 0 < len(clean_math) < 150 and (
            any(char in clean_math for char in "xyz√π∫^")
            or ("=" in clean_math and len(clean_math) > 3)
        ):
            latex_math = clean_math.replace("≈", r"\approx").replace(
                "integral", r"\int"
            )
            embed.set_image(
                url=(
                    rf"https://latex.codecogs.com/png.image?"
                    rf"\dpi{150} \bgwhite {quote(latex_math)}"
                )
            )

        embed.set_footer(text=f"Query: {query}")
        return embed

    @commands.hybrid_command(
        name="math",
        aliases=["wa", "wolfram", "mq"],
        help="Answers math queries locally or via Wolfram Alpha.",
    )
    @app_commands.describe(query="The math problem, function to plot, or question.")
    async def math(self, ctx, *, query: str):
        await ctx.defer()

        # Handle Plotting (both "plot" and "graph" keywords)
        query_lower = query.lower()
        if "plot" in query_lower or "graph" in query_lower:
            # Remove the first occurrence of "plot" or "graph"
            func = query_lower.replace("plot", "").replace("graph", "", 1).strip()
            await self.plot_function(ctx, func)
            return

        # Handle Calculation
        local_result = self.solve_locally(query)
        if local_result:
            await ctx.send(
                embed=self.create_embed("Local Math Result", local_result, query)
            )
            return

        short_result = await self.query_short_answer(query)
        if short_result and "did not understand" not in short_result.lower():
            await ctx.send(
                embed=self.create_embed("Wolfram Alpha Result", short_result, query)
            )
            return

        full_result = await self.query_llm_api(query)
        if full_result:
            await ctx.send(
                embed=self.create_embed("Wolfram Alpha Result", full_result, query)
            )
        else:
            await ctx.send("Sorry, I couldn't find an answer to your query.")

    async def query_short_answer(self, query: str) -> str | None:
        if not WOLFRAM_SHORT_APPID:
            return None
        url = "https://api.wolframalpha.com/v1/result"
        params = {"appid": WOLFRAM_SHORT_APPID, "i": query, "units": "metric"}
        try:
            async with (
                aiohttp.ClientSession() as session,
                session.get(url, params=params) as resp,
            ):
                if resp.status == 200:
                    return await resp.text()
                return None
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return None

    async def query_llm_api(self, query: str) -> str | None:
        if not WOLFRAM_LLM_APPID:
            return None
        url = "https://www.wolframalpha.com/api/v1/llm-api"
        params = {
            "appid": WOLFRAM_LLM_APPID,
            "input": query,
            "units": "metric",
        }
        try:
            async with (
                aiohttp.ClientSession() as session,
                session.get(url, params=params) as resp,
            ):
                if resp.status == 200:
                    content_type = resp.headers.get("content-type", "").lower()
                    if "application/json" in content_type:
                        data = await resp.json()
                        return str(data.get("result"))
                    return await resp.text()
                return None
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return None


async def setup(bot):
    await bot.add_cog(MathCog(bot))
