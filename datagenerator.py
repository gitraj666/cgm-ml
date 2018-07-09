import os
import numpy as np
import glob2
import json
import random
import keras.preprocessing.image as image_preprocessing
import progressbar
from pyntcloud import PyntCloud


class DataGenerator(object):

    def __init__(
        self,
        dataset_path,
        input_type,
        output_targets,
        image_target_shape=(160, 90),
        voxelgrid_target_shape=(32, 32, 32),
        pointcloud_target_size=32000
        ):

        # Preconditions.
        assert os.path.exists(dataset_path), "dataset_path must exist: " + str(dataset_path)
        assert isinstance(input_type, str), "input_type must be string: " + str(input_type)
        assert isinstance(output_targets, list), "output_targets must be list: " + str(output_targets)
        assert len(image_target_shape) == 2, "image_target_shape must be 2-dimensional: " + str(image_target_shape)
        assert len(voxelgrid_target_shape) == 3, "voxelgrid_target_shape must be 3-dimensional: " + str(voxelgrid_target_shape)

        # Assign the instance-variables.
        self.dataset_path = dataset_path
        self.input_type = input_type
        self.output_targets = output_targets
        self.image_target_shape = image_target_shape
        self.voxelgrid_target_shape = voxelgrid_target_shape
        self.pointcloud_target_size = pointcloud_target_size

        # Create some caches.
        self.image_cache = {}
        self.voxelgrid_cache = {}
        self.pointcloud_cache = {}

        # Get all the paths.
        self._get_paths()

        # Find all QR-codes.
        self._find_qrcodes()
        assert self.qrcodes != [], "No QR-codes found!"

        # Create the QR-codes dictionary.
        self._create_qrcodes_dictionary()


    def _get_paths(self):

        # Getting the paths for images.
        glob_search_path = os.path.join(self.dataset_path, "storage/person", "**/*.jpg")
        self.jpg_paths = glob2.glob(glob_search_path)

        # Getting the paths for point clouds.
        glob_search_path = os.path.join(self.dataset_path, "storage/person", "**/*.pcd")
        self.pcd_paths = glob2.glob(glob_search_path)

        # Getting the paths for personal and measurement.
        glob_search_path = os.path.join(self.dataset_path, "**/*.json")
        json_paths = glob2.glob(glob_search_path)
        self.json_paths_personal = [json_path for json_path in json_paths if "measures" not in json_path]
        self.json_paths_measures = [json_path for json_path in json_paths if "measures" in json_path]
        del json_paths


    def _find_qrcodes(self):

        qrcodes = []
        for json_path_measure in self.json_paths_measures:
            json_data_measure = json.load(open(json_path_measure))
            qrcode = self._extract_qrcode(json_data_measure)
            qrcodes.append(qrcode)
        qrcodes = sorted(list(set(qrcodes)))

        self.qrcodes = qrcodes


    def _create_qrcodes_dictionary(self):

        qrcodes_dictionary = {}

        for json_path_measure in self.json_paths_measures:
            json_data_measure = json.load(open(json_path_measure))

            # Ensure manual data.
            if json_data_measure["type"]["value"] != "manual":
                continue

            # Extract the QR-code.
            qrcode = self._extract_qrcode(json_data_measure)

            # In the future there will be multiple manual measurements. Handle this!
            if qrcode in qrcodes_dictionary.keys():
                raise Exception("Multiple manual measurements for QR-code: " + qrcode)

            # Extract the targets.
            targets = self._extract_targets(json_data_measure)
            jpg_paths = [jpg_path for jpg_path in self.jpg_paths if qrcode in jpg_path and "measurements" in jpg_path]
            pcd_paths = [pcd_path for pcd_path in self.pcd_paths if qrcode in pcd_path and "measurements" in pcd_path]

            qrcodes_dictionary[qrcode] = targets, jpg_paths, pcd_paths

        self.qrcodes_dictionary = qrcodes_dictionary


    def _extract_targets(self, json_data_measure):
        targets = []
        for output_target in self.output_targets:
            value = json_data_measure[output_target]["value"]
            targets.append(value)
        return targets


    def _extract_qrcode(self, json_data_measure):
        person_id = json_data_measure["personId"]["value"]
        json_path_personal = [json_path for json_path in self.json_paths_personal if person_id in json_path]
        assert len(json_path_personal) == 1
        json_path_personal = json_path_personal[0]
        json_data_personal = json.load(open(json_path_personal))
        qrcode = json_data_personal["qrcode"]["value"]
        return qrcode


    def _load_image(self, image_path):
        image = self.image_cache.get(image_path, [])
        if image == []:
            image = image_preprocessing.load_img(image_path, target_size=self.image_target_shape)
            image = image.rotate(-90, expand=True)
            image = np.array(image)
            self.voxelgrid_cache[image_path] = image
        return image


    def _load_voxelgrid(self, pcd_path):
        voxelgrid = self.voxelgrid_cache.get(pcd_path, [])
        if voxelgrid == []:
            points = PyntCloud.from_file(pcd_path)
            #voxelgrid_id = points.add_structure("voxelgrid", size_x=0.005, size_y=0.005, size_z=0.005)
            voxelgrid_id = points.add_structure("voxelgrid", n_x=self.voxelgrid_target_shape[0], n_y=self.voxelgrid_target_shape[1], n_z=self.voxelgrid_target_shape[2])
            voxelgrid = points.structures[voxelgrid_id]
            voxelgrid = voxelgrid.get_feature_vector(mode="density")
            self.voxelgrid_cache[pcd_path] = voxelgrid
        return voxelgrid


    def _load_pointcloud(self, pcd_path):
        pointcloud = self.pointcloud_cache.get(pcd_path, [])
        if pointcloud == []:
            pointcloud = PyntCloud.from_file(pcd_path).points.values
            pointcloud = pointcloud[:self.pointcloud_target_size]
            pointcloud = np.array(pointcloud)
            assert pointcloud.shape == (pointcloud_target_size, 4), pcd_path + " " + str(pointcloud.shape)
            self.pointcloud_cache[pcd_path] = pointcloud
        return pointcloud


    def get_input_shape(self):

        if self.input_type == "image":
            return (90, 160, 3)

        elif self.input_type == "voxelgrid":
            return (32, 32, 32)

        elif self.input_type == "pointcloud":
            return (32000, 4)

        else:
            raise Exception("Unknown input_type: " + input_type)


    def get_output_size(self):

        return len(self.output_targets)


    def generate(self, size, qrcodes_to_use=None, verbose=False):

        if qrcodes_to_use == None:
            qrcodes_to_use = self.qrcodes

        while True:

            x_inputs = []
            y_outputs = []

            if verbose == True:
                bar = progressbar.ProgressBar(max_value=size)
            while len(x_inputs) < size:

                # Get a random QR-code.
                qrcode = random.choice(qrcodes_to_use)

                # Get targets and paths.
                if qrcode not in  self.qrcodes_dictionary.keys():
                    continue
                targets, jpg_paths, pcd_paths = self.qrcodes_dictionary[qrcode]

                # Get a random image.
                if self.input_type == "image":
                    if len(jpg_paths) == 0:
                        continue
                    jpg_path = random.choice(jpg_paths)
                    image = self._load_image(jpg_path)
                    x_input = image

                # Get a random voxelgrid.
                elif self.input_type == "voxelgrid":
                    if len(pcd_paths) == 0:
                        continue
                    pcd_path = random.choice(pcd_paths)
                    try:
                        voxelgrid = self._load_voxelgrid(pcd_path)
                    except Exception as e:
                        #print(e)
                        #print("Error:", pcd_path)
                        continue
                    x_input = voxelgrid

                # Get a random pointcloud.
                elif self.input_type == "pointcloud":
                    if len(pcd_paths) == 0:
                        continue
                    pcd_path = random.choice(pcd_paths)
                    try:
                        pointcloud = self._load_pointcloud(pcd_path)
                    except Exception as e:
                        #print(e)
                        #print("Error:", pcd_path)
                        continue
                    x_input = pointcloud

                else:
                    raise Exception("Unknown input_type: " + input_type)

                y_output = targets

                x_inputs.append(x_input)
                y_outputs.append(y_output)

                if verbose == True:
                    bar.update(len(x_inputs))

            if verbose == True:
                bar.finish()

            x_inputs = np.array(x_inputs)
            y_outputs = np.array(y_outputs)

            yield x_inputs, y_outputs


    def generate_dataset(self, qrcodes_to_use=None):

        if qrcodes_to_use == None:
            qrcodes_to_use = self.qrcodes

        x_qrcodes = []
        x_inputs = []
        y_outputs = []
        for index, qrcode in enumerate(qrcodes_to_use):

            print("Processing:", qrcode)

            # Get targets and paths.
            if qrcode not in  self.qrcodes_dictionary.keys():
                print("No data for:", qrcode)
                continue
            targets, jpg_paths, pcd_paths = self.qrcodes_dictionary[qrcode]
            print(targets)

            # Process image.
            if self.input_type == "image":

                for jpg_path in jpg_paths:
                    image = self._load_image(jpg_path)
                    x_qrcodes.append(qrcode)
                    x_inputs.append(image)
                    y_outputs.append(targets)


            # Process voxelgrid.
            elif self.input_type == "voxelgrid":

                for pcd_path in pcd_paths:
                    try:
                        voxelgrid = self._load_voxelgrid(pcd_path)
                    except Exception as e:
                        print(e)
                        print("Error:", pcd_path)

                    x_qrcodes.append(qrcode)
                    x_inputs.append(voxelgrid)
                    y_outputs.append(targets)

            # Process pointcloud.
            elif self.input_type == "pointcloud":

                for pcd_path in pcd_paths:
                    try:
                        pointcloud = self._load_pointcloud(pcd_path)
                    except Exception as e:
                        print(e)
                        print("Error:", pcd_path)
                        continue

                    x_qrcodes.append(qrcode)
                    x_inputs.append(pointcloud)
                    y_outputs.append(targets)

            else:
                raise Exception("Unknown input_type: " + input_type)

        x_qrcodes = np.array(x_qrcodes)
        x_inputs = np.array(x_inputs)
        y_outputs = np.array(y_outputs)

        return x_qrcodes, x_inputs, y_outputs


def test_generator():

    if os.path.exists("datasetpath.txt"):
        dataset_path = open("datasetpath.txt", "r").read().replace("\n", "")
    else:
        dataset_path = "../data"

    data_generator = DataGenerator(dataset_path=dataset_path, input_type="voxelgrid", output_targets=["height", "weight"])

    print("jpg_paths", len(data_generator.jpg_paths))
    print("pcd_paths", len(data_generator.jpg_paths))
    print("json_paths_personal", len(data_generator.jpg_paths))
    print("json_paths_measures", len(data_generator.jpg_paths))
    print("QR-Codes:\n" + "\n".join(data_generator.qrcodes))
    #print(data_generator.qrcodes_dictionary)

    qrcodes_shuffle = list(data_generator.qrcodes)
    random.shuffle(qrcodes_shuffle)
    split_index = int(0.8 * len(qrcodes_shuffle))
    qrcodes_train = qrcodes_shuffle[:split_index]
    qrcodes_validate = qrcodes_shuffle[split_index:]

    print("Training data:")
    x_train, y_train = next(data_generator.generate(size=200, qrcodes_to_use=qrcodes_train))
    print(x_train.shape)
    print(y_train.shape)
    print("")

    print("Validation data:")
    x_validate, y_validate = next(data_generator.generate(size=20, qrcodes_to_use=qrcodes_validate))
    print(x_validate.shape)
    print(y_validate.shape)
    print("")


def test_dataset():

    if os.path.exists("datasetpath.txt"):
        dataset_path = open("datasetpath.txt", "r").read().replace("\n", "")
    else:
        dataset_path = "../data"

    data_generator = DataGenerator(dataset_path=dataset_path, input_type="image", output_targets=["height", "weight"])

    x_qrcodes, x_inputs, y_outputs = data_generator.generate_dataset(data_generator.qrcodes[0:4])
    print(len(x_qrcodes))


def test_parameters():

    if os.path.exists("datasetpath.txt"):
        dataset_path = open("datasetpath.txt", "r").read().replace("\n", "")
    else:
        dataset_path = "../data"

    print("Testing image...")
    data_generator = DataGenerator(dataset_path=dataset_path, input_type="image", output_targets=["height", "weight"], image_target_shape=(20,20))
    x_input, y_output = next(data_generator.generate(size=1))
    assert x_input.shape[1:3] == (20,20)

    print("Testing voxelgrid...")
    data_generator = DataGenerator(dataset_path=dataset_path, input_type="voxelgrid", output_targets=["height", "weight"], voxelgrid_target_shape=(20, 20, 20))
    x_input, y_output = next(data_generator.generate(size=1))
    assert x_input.shape[1:] == (20, 20, 20)

    print("Testing pointcloud...")
    data_generator = DataGenerator(dataset_path=dataset_path, input_type="pointcloud", output_targets=["height", "weight"], pointcloud_target_size=16000)
    x_input, y_output = next(data_generator.generate(size=1))
    assert x_input.shape[1:] == (20, 4)

    print("Done.")


if __name__ == "__main__":
    #test_generator()
    #test_dataset()
    test_parameters()
