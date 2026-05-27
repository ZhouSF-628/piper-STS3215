# Vendored from LeRobot (Apache 2.0)
import importlib
import importlib.metadata
import logging


def is_package_available(
    pkg_name: str, import_name: str | None = None, return_version: bool = False
) -> tuple[bool, str] | bool:
    if import_name is None:
        import_name = pkg_name
    package_exists = importlib.util.find_spec(import_name) is not None
    package_version = "N/A"
    if package_exists:
        try:
            package_version = importlib.metadata.version(pkg_name)
        except importlib.metadata.PackageNotFoundError:
            if pkg_name == "torch":
                try:
                    package = importlib.import_module(import_name)
                    temp_version = getattr(package, "__version__", "N/A")
                    if "dev" in temp_version:
                        package_version = temp_version
                        package_exists = True
                    else:
                        package_exists = False
                except ImportError:
                    package_exists = False
            else:
                package_exists = False
        logging.debug(f"Detected {pkg_name} version: {package_version}")
    if return_version:
        return package_exists, package_version
    else:
        return package_exists


_require_package_cache: dict[str, bool] = {}


def require_package(pkg_name: str, extra: str, import_name: str | None = None) -> None:
    cache_key = import_name or pkg_name
    if cache_key not in _require_package_cache:
        _require_package_cache[cache_key] = is_package_available(pkg_name, import_name)
    if not _require_package_cache[cache_key]:
        raise ImportError(
            f"'{pkg_name}' is required but not installed. Install it with: "
            f"pip install 'lerobot[{extra}]'"
        )


_serial_available = is_package_available("pyserial", import_name="serial")
_deepdiff_available = is_package_available("deepdiff")
_feetech_sdk_available = is_package_available("feetech-servo-sdk", import_name="scservo_sdk")
