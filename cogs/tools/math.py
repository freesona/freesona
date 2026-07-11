# cogs/tools/math.py: Local, Wolfram Alpha, and Visualization solution

import os
# Force SymPy to use SymEngine as the primary backend BEFORE importing sympy
os.environ["SYMPY_BACKEND"] = "symengine"

import logging
try:
    import symengine
    logging.info("SymEngine successfully loaded as the symbolic backend.")
except ImportError:
    logging.warning("SymEngine not found. Falling back to default SymPy.")

import ast
import asyncio
import aiohttp
import re
import discord
import sympy
import numpy as np
import io
from discord.ext import commands

try:
    from matplotlib.figure import Figure
except ImportError:
    Figure = None
from discord import app_commands
from urllib.parse import quote
from dotenv import load_dotenv

load_dotenv()

WOLFRAM_SHORT_APPID = os.getenv("WOLFRAM_APPID_SHORT")
WOLFRAM_LLM_APPID = os.getenv("WOLFRAM_APPID_LLM")

SAFE_FUNCTIONS = {
    'sin', 'cos', 'tan', 'cot', 'sec', 'csc',
    'asin', 'acos', 'atan', 'acot', 'asec', 'acsc',
    'sinh', 'cosh', 'tanh', 'coth', 'sech', 'csch',
    'asinh', 'acosh', 'atanh', 'acoth', 'asech', 'acsch',
    'sqrt', 'cbrt', 'exp', 'log', 'ln', 'log10', 'abs',
    'factorial', 'gamma', 'floor', 'ceiling',
    'limit', 'diff', 'integrate', 'solve', 'expand', 'simplify',
    'pi', 'E', 'e', 'I', 'oo', 'Infinity', 'nan',
    'summation', 'product', 'root', 'N', 'evalf'
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
        ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod, ast.FloorDiv,
        ast.UAdd, ast.USub,
        ast.Load, ast.Store, ast.Del,
    )
    
    if not isinstance(node, allowed_nodes):
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float, complex, bool)) or node.value is None:
                return True
        return False

    if isinstance(node, ast.Name):
        if node.id.startswith('__') or node.id in {'eval', 'exec', 'open', 'import', 'print', 'getattr', 'setattr', 'delattr', 'compile', 'globals', 'locals'}:
            return False
        return True

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
        if '#' in query or ';' in query:
            return False
        tree = ast.parse(query, mode='eval')
        return check_ast_safe(tree)
    except Exception:
        return False

def _minimal_png_placeholder() -> io.BytesIO:
    buf = io.BytesIO()
    buf.write(
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc`\x00\x00\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    buf.seek(0)
    return buf


def generate_plot(func_str: str) -> io.BytesIO:
    if Figure is None:
        return _minimal_png_placeholder()

    clean_func = func_str.replace('^', '**')
    x_symbol = sympy.Symbol('x')
    expr = sympy.sympify(clean_func, evaluate=True)
    y_func = sympy.lambdify(x_symbol, expr, "numpy")
    
    x = np.linspace(-10, 10, 400)
    with np.errstate(divide='ignore', invalid='ignore'):
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
    fig.savefig(buf, format='png')
    buf.seek(0)
    return buf

class MathCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def solve_locally(self, query: str) -> str | None:
        try:
            clean_query = query.replace('^', '**')
            
            # 1. Critical safety validation
            if not is_safe_expression(clean_query):
                logging.warning(f"Unsafe expression blocked: {query}")
                return None
                
            parsed_expr = sympy.sympify(clean_query, evaluate=False)
            result = sympy.sympify(clean_query, evaluate=True)
            
            # If the result is a SymPy Symbol, it's just a variable name (unsimplified/unsolved)
            if getattr(result, 'is_Symbol', False):
                return None
                
            is_sympy_obj = hasattr(result, 'is_number')
            is_different = (result != parsed_expr)
            is_number = is_sympy_obj and result.is_number
            is_container = isinstance(result, (list, tuple, dict, set))
            
            if is_different or is_number or is_container:
                if is_number and not isinstance(result, (list, tuple, dict, set)):
                    if not getattr(result, 'is_Integer', False):
                        evalf_fn = getattr(result, 'evalf', None)
                        if evalf_fn:
                            raw_float = str(evalf_fn(10))
                            if '.' in raw_float:
                                return raw_float.rstrip('0').rstrip('.')
                            return raw_float
                return str(result)
                
            return None
        except Exception as e:
            logging.debug(f"Local solve failed: {e}")
            return None

    async def plot_function(self, ctx, func_str: str):
        # 1. Clean input
        func_str_clean = func_str.strip()
        if not func_str_clean:
            await ctx.send("Please provide a mathematical function of `x` to plot (e.g., `x**2` or `sin(x)`).")
            return
            
        # 2. Critical safety validation
        if not is_safe_expression(func_str_clean.replace('^', '**')):
            await ctx.send("Error: Unsafe characters or expressions detected in the plotting query.")
            return

        # 3. Offload blocking matplotlib rendering to a separate thread
        try:
            buf = await asyncio.to_thread(generate_plot, func_str_clean)
        except Exception as e:
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
        text = re.sub(r'(?i)Wolfram Language code:.*', '', text)
        text = re.sub(r'(?i)Wolfram\s*\|\s*Alpha website result.*', '', text)
        text = re.sub(r'(?i)Input interpretation:.*?\n', '', text)
        text = re.sub(r'(?i)Result:\s*\n*', '', text)
        text = re.sub(r'(?i)(plot|image|url):\s*https?://\S+', '', text)
        text = re.sub(r'https?://\S+', '', text)
        text = re.sub(r'(?m)^([^:\n|]+)\s*\|\s*([^\n]+)', r'**\1** | \2', text)
        text = re.sub(r'\n\s*\n', '\n', text)
        return text.strip()

    def create_embed(self, title: str, content: str, query: str) -> discord.Embed:
        formatted_content = self.format_wolfram_text(content)
        embed = discord.Embed(title=title, description=formatted_content[:4096] or "No result found.", color=0xDA5B40)
        clean_math = formatted_content.replace('**', '').replace('`', '').strip()
        
        if 0 < len(clean_math) < 150:
            if any(char in clean_math for char in 'xyz√π∫^') or ('=' in clean_math and len(clean_math) > 3):
                latex_math = clean_math.replace('≈', r'\approx').replace('integral', r'\int')
                embed.set_image(url=fr"https://latex.codecogs.com/png.image?\dpi{{150}}\bg{{white}}{quote(latex_math)}")

        embed.set_footer(text=f"Query: {query}")
        return embed

    @commands.hybrid_command(name="math", aliases=['wa', 'wolfram', 'mq'], help="Answers math queries locally or via Wolfram Alpha.")
    @app_commands.describe(query="The math problem, function to plot, or question.")
    async def math(self, ctx, *, query: str):
        await ctx.defer()
        
        # Handle Plotting
        if "plot" in query.lower():
            func = query.lower().replace("plot", "").strip()
            await self.plot_function(ctx, func)
            return

        # Handle Calculation
        local_result = self.solve_locally(query)
        if local_result:
            await ctx.send(embed=self.create_embed("Local Math Result", local_result, query))
            return

        short_result = await self.query_short_answer(query)
        if short_result and "did not understand" not in short_result.lower():
            await ctx.send(embed=self.create_embed("Wolfram Alpha Result", short_result, query))
            return
        
        full_result = await self.query_llm_api(query)
        if full_result:
            await ctx.send(embed=self.create_embed("Wolfram Alpha Result", full_result, query))
        else:
            await ctx.send("Sorry, I couldn't find an answer to your query.")

    async def query_short_answer(self, query: str) -> str | None:
        if not WOLFRAM_SHORT_APPID: return None
        url = "http://api.wolframalpha.com/v1/result"
        params = {"appid": WOLFRAM_SHORT_APPID, "i": query, "units": "metric"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    if resp.status == 200: return await resp.text()
                    return None
        except Exception: return None

    async def query_llm_api(self, query: str) -> str | None:
        if not WOLFRAM_LLM_APPID: return None
        url = "https://www.wolframalpha.com/api/v1/llm-api"
        params = {"appid": WOLFRAM_LLM_APPID, "input": query, "units": "metric"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        content_type = resp.headers.get('content-type', '').lower()
                        if 'application/json' in content_type:
                            data = await resp.json()
                            return str(data.get("result"))
                        return await resp.text()
                    return None
        except Exception: return None

async def setup(bot):
    await bot.add_cog(MathCog(bot))