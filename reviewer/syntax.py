import ast
import json
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None


class SyntaxChecker:
    """
    Language-aware syntax validation.

    Returns:
        list[str]: Empty if valid, otherwise one or more error messages.
    """

    def check(
        self,
        path: str,
        content: str,
    ) -> list[str]:

        suffix = Path(path).suffix.lower()

        if suffix == ".py":
            return self._check_python(path, content)

        if suffix == ".json":
            return self._check_json(path, content)

        if suffix in {".yaml", ".yml"}:
            return self._check_yaml(path, content)

        # Future:
        #
        # if suffix == ".java":
        #     return self._check_java(...)
        #
        # if suffix in {".js", ".ts"}:
        #     return self._check_javascript(...)

        return []

    @staticmethod
    def _snippet(
        content: str,
        lineno: int,
        context: int = 2,
    ) -> str:
        """
        Return a few lines around the error location.
        """

        lines = content.splitlines()

        start = max(0, lineno - 1 - context)
        end = min(len(lines), lineno + context)

        return "\n".join(
            f"{i + 1:>4} | {line}"
            for i, line in enumerate(
                lines[start:end],
                start,
            )
        )

    @classmethod
    def _check_python(
        cls,
        path: str,
        content: str,
    ) -> list[str]:

        try:
            ast.parse(content)

        except SyntaxError as e:

            lineno = e.lineno or 1
            snippet = cls._snippet(content, lineno)

            return [
                (
                    f"{path}:{lineno}:{e.offset}: {e.msg}\n\n"
                    f"{snippet}"
                )
            ]

        return []

    @classmethod
    def _check_json(
        cls,
        path: str,
        content: str,
    ) -> list[str]:

        try:
            json.loads(content)

        except json.JSONDecodeError as e:

            snippet = cls._snippet(
                content,
                e.lineno,
            )

            return [
                (
                    f"{path}:{e.lineno}:{e.colno}: {e.msg}\n\n"
                    f"{snippet}"
                )
            ]

        return []

    @classmethod
    def _check_yaml(
        cls,
        path: str,
        content: str,
    ) -> list[str]:

        if yaml is None:
            return [
                (
                    f"{path}: YAML validation unavailable "
                    "(PyYAML is not installed)."
                )
            ]

        try:
            yaml.safe_load(content)

        except yaml.YAMLError as e:

            mark = getattr(
                e,
                "problem_mark",
                None,
            )

            if mark is None:
                return [
                    f"{path}: invalid YAML\n{e}"
                ]

            lineno = mark.line + 1
            col = mark.column + 1

            snippet = cls._snippet(
                content,
                lineno,
            )

            return [
                (
                    f"{path}:{lineno}:{col}: {e}\n\n"
                    f"{snippet}"
                )
            ]

        return []