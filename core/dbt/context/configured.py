from typing import Any, Dict, Iterable, Union

from dbt.clients.jinja import MacroProxy
from dbt.contracts.connection import AdapterRequiredConfig
from dbt.contracts.graph.manifest import Manifest
from dbt.contracts.graph.parsed import ParsedMacro
from dbt.include.global_project import PACKAGES
from dbt.include.global_project import PROJECT_NAME as GLOBAL_PROJECT_NAME

from dbt.context.base import contextproperty
from dbt.context.target import TargetContext
from dbt.exceptions import raise_duplicate_macro_name


class ConfiguredContext(TargetContext):
    config: AdapterRequiredConfig

    def __init__(
        self, config: AdapterRequiredConfig
    ) -> None:
        super().__init__(config, config.cli_vars)

    @contextproperty
    def project_name(self) -> str:
        return self.config.project_name


Namespace = Union[Dict[str, MacroProxy], MacroProxy]


class _MacroNamespace:
    def __init__(self, root_package, search_package):
        self.root_package = root_package
        self.search_package = search_package
        self.globals: Dict[str, MacroProxy] = {}
        self.locals: Dict[str, MacroProxy] = {}
        self.packages: Dict[str, Dict[str, MacroProxy]] = {}

    def add_macro(self, macro: ParsedMacro, ctx: Dict[str, Any]):
        macro_name: str = macro.name
        macro_func: MacroProxy = macro.generator(ctx)

        # put plugin macros into the root namespace
        if macro.package_name in PACKAGES:
            namespace: str = GLOBAL_PROJECT_NAME
        else:
            namespace = macro.package_name

        if namespace not in self.packages:
            value: Dict[str, MacroProxy] = {}
            self.packages[namespace] = value

        if macro_name in self.packages[namespace]:
            raise_duplicate_macro_name(macro_func.node, macro, namespace)
        self.packages[namespace][macro_name] = macro_func

        if namespace == self.search_package:
            self.locals[macro_name] = macro_func
        elif namespace in {self.root_package, GLOBAL_PROJECT_NAME}:
            self.globals[macro_name] = macro_func

    def add_macros(self, macros: Iterable[ParsedMacro], ctx: Dict[str, Any]):
        for macro in macros:
            self.add_macro(macro, ctx)

    def get_macro_dict(self) -> Dict[str, Any]:
        root_namespace: Dict[str, Namespace] = {}

        root_namespace.update(self.packages)
        root_namespace.update(self.globals)
        root_namespace.update(self.locals)

        return root_namespace


class ManifestContext(ConfiguredContext):
    """The Macro context has everything in the target context, plus the macros
    in the manifest.

    The given macros can override any previous context values, which will be
    available as if they were accessed relative to the package name.
    """
    def __init__(
        self,
        config: AdapterRequiredConfig,
        manifest: Manifest,
        search_package: str,
    ) -> None:
        super().__init__(config)
        self.manifest = manifest
        self.search_package = search_package

    def get_macros(self) -> Dict[str, Any]:
        nsp = _MacroNamespace(self.config.project_name, self.search_package)
        nsp.add_macros(self.manifest.macros.values(), self._ctx)
        return nsp.get_macro_dict()

    def to_dict(self) -> Dict[str, Any]:
        dct = super().to_dict()
        dct.update(self.get_macros())
        return dct


class QueryHeaderContext(ManifestContext):
    def __init__(
        self, config: AdapterRequiredConfig, manifest: Manifest
    ) -> None:
        super().__init__(config, manifest, config.project_name)


def generate_query_header_context(
    config: AdapterRequiredConfig, manifest: Manifest
):
    ctx = QueryHeaderContext(config, manifest)
    return ctx.to_dict()
