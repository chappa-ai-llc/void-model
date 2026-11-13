"""Load pickle files without running arbitrary code.

``pickle.load`` on a file you did not write yourself can run any code the
file asks for. ``safe_load`` refuses every global except plain built-in
containers and the NumPy names needed to rebuild arrays, so a hostile file
fails with ``pickle.UnpicklingError`` instead of executing.

This module is copied to ``data_generation/safe_pickle.py`` for the Blender
scripts, which do not import the ``videox_fun`` package; keep both the same
(``tests/test_security.py`` checks that they are).
"""

import io
import pickle

__all__ = ["safe_load", "safe_loads", "ALLOWED_GLOBALS"]

ALLOWED_GLOBALS = frozenset({
    ("builtins", "dict"), ("builtins", "list"), ("builtins", "tuple"),
    ("builtins", "set"), ("builtins", "frozenset"), ("builtins", "str"),
    ("builtins", "bytes"), ("builtins", "bytearray"), ("builtins", "int"),
    ("builtins", "float"), ("builtins", "complex"), ("builtins", "bool"),
    ("builtins", "slice"), ("builtins", "range"),
    ("collections", "OrderedDict"), ("collections", "defaultdict"),
    # NumPy array, scalar and dtype reconstruction (NumPy 1.x and 2.x paths).
    ("numpy", "ndarray"), ("numpy", "dtype"),
    ("numpy.core.multiarray", "_reconstruct"), ("numpy.core.multiarray", "scalar"),
    ("numpy._core.multiarray", "_reconstruct"), ("numpy._core.multiarray", "scalar"),
    ("numpy.core.numeric", "_frombuffer"), ("numpy._core.numeric", "_frombuffer"),
})


class _RestrictedUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        if (module, name) in ALLOWED_GLOBALS:
            return super().find_class(module, name)
        # NumPy pickles dtypes of fixed-width scalars as numpy.dtypes.<Name>DType.
        if module == "numpy.dtypes" and name.endswith("DType"):
            return super().find_class(module, name)
        raise pickle.UnpicklingError(
            f"refusing to load {module}.{name} from a pickle file: only plain data "
            "and NumPy arrays are allowed (see safe_pickle.ALLOWED_GLOBALS)"
        )


def safe_load(file):
    """Like ``pickle.load(file)``, but only for plain data and NumPy arrays."""
    return _RestrictedUnpickler(file).load()


def safe_loads(data):
    """Like ``pickle.loads(data)``, but only for plain data and NumPy arrays."""
    return _RestrictedUnpickler(io.BytesIO(data)).load()
