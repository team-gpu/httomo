from typing import Dict
import numpy as np
from mpi4py.MPI import Comm

from httomo.utils import pattern, Pattern
from httomolib import misc


@pattern(Pattern.all)
def images(params: Dict, method_name: str, out_dir: str, comm: Comm, data: np.ndarray) -> np.ndarray:
    """Wrapper for httomolib.misc.images module.

    Parameters
    ----------
    params : Dict
        A dict containing all params of the wrapped tomopy function that are
        independent of httomo.
    method_name : str
        The name of the method to use in httomolib.misc.corr.
    out_dir : str
        The output directory.
    comm: int
        the MPI communicator.
    data : ndarray
        A CuPy data array.

    Returns
    -------
    """
    
    module = getattr(misc, 'images')
    comm_rank = comm.rank
    data = getattr(module, method_name)(data, out_dir, comm_rank = comm_rank, **params)
    return data