import os

import numpy as np
import zarr
import numcodecs
from numcodecs import Blosc

from simrecorder.datastore import DataStore

numcodecs.blosc.set_nthreads(16)


class ZarrDataStore(DataStore):
    """
    This is a zarr datastore.
    """

    def __init__(self, data_dir_pth, desired_chunk_size_bytes=0.1 * 1024**2):
        """
        :param data_dir_pth: Path to the hdf5 file
        self.desired_chunk_size_bytes = desired_chunk_size_bytes
        """

        self.store = zarr.LMDBStore(data_dir_pth)
        self.compressor = Blosc(cname='lz4', clevel=9)    # , shuffle=Blosc.BITSHUFFLE)

        self.desired_chunk_size_bytes = desired_chunk_size_bytes

        if not os.path.exists(data_dir_pth):
            self.f = zarr.group(store=self.store, overwrite=True)
        else:
            self.f = zarr.group(store=self.store, overwrite=False)

        self.i = 0

    def set(self, key, dict_obj):
        for k, v in dict_obj.items():
            self.f.create_dataset("{}/{}".format(key, k), data=v)

    def get(self, key):
        return self.f.get(key)

    def append(self, key, obj):
        if isinstance(obj, np.ndarray):
            d = self.f.get(key)
            if d is not None:
                assert isinstance(d, zarr.core.Array)
                # https://stackoverflow.com/a/25656175
                d.resize(d.shape[0] + 1, *d.shape[1:])
                d[-1, ...] = obj
                self.store.flush()
            else:
                self.f.create_dataset(
                    key, data=obj[None, ...], compressor=self.compressor, chunks=self._get_chunk_size(obj))
        else:
            self.f.create_dataset("{}/{}".format(key, self.i), data=obj)
            self.i += 1

    def _get_chunk_size(self, obj):
        """
        Tries to optimize the chunk size (assuming 32-bit floats used) so that the chunk size is close to 1MB. The last
        dimension size is maintained without change.
        :param obj:
        :return:
        """
        ## Makes sure chunk size is always 1MB!
        desired_chunk_size_bytes = self.desired_chunk_size_bytes    # 8K # 1024**2  # 1MB
        if desired_chunk_size_bytes <= 0:
            # Switch to h5py's automagic chunk size calculation
            return True

        element_size_bytes = 4
        # Assuming storage of 32-bit floats
        if np.prod(obj.shape) * element_size_bytes <= desired_chunk_size_bytes:
            return tuple([1] + list(obj.shape))
        else:
            ndim = len(obj.shape)
            total_elements = desired_chunk_size_bytes / element_size_bytes
            cum_el = total_elements
            last_el_s = obj.shape[-1]
            cum_el /= last_el_s
            shape = [1]
            for i in range(ndim - 1):
                s = np.minimum(obj.shape[i], np.power(cum_el, 1 / (ndim - i - 1)))
                s = np.floor(s)
                cum_el /= s
                shape.append(int(s))
            shape.append(int(last_el_s))
            assert len(shape) == len(obj.shape) + 1
            return tuple(shape)

    def get_all(self, key):
        d = self.f.get(key)
        if d is not None:
            if isinstance(d, zarr.core.Array):
                return d
            else:
                return list(map(lambda x: x[1], sorted(d.items(), key=lambda x: int(x[0]))))

    def close(self):
        self.store.close()
