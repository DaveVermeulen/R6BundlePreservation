#!/usr/bin/env python3
"""
Roblox .mesh to .obj Converter
Supports mesh versions 1.00 - 7.00 including Draco compression
"""

import struct
import sys
import io
from typing import BinaryIO, Tuple, List, Optional
import math


class ByteReader:
    """Binary file reader with support for various data types"""
    
    def __init__(self, data: bytes):
        self.data = data
        self.index = 0
        self.length = len(data)
    
    def get_remaining(self) -> int:
        return self.length - self.index
    
    def get_index(self) -> int:
        return self.index
    
    def set_index(self, n: int):
        self.index = n
    
    def jump(self, n: int):
        self.index += n
    
    def array(self, n: int) -> bytes:
        result = self.data[self.index:self.index + n]
        self.index += n
        return result
    
    def uint8(self) -> int:
        val = self.data[self.index]
        self.index += 1
        return val
    
    def uint16_le(self) -> int:
        val = struct.unpack('<H', self.data[self.index:self.index + 2])[0]
        self.index += 2
        return val
    
    def uint32_le(self) -> int:
        val = struct.unpack('<I', self.data[self.index:self.index + 4])[0]
        self.index += 4
        return val
    
    def float_le(self) -> float:
        val = struct.unpack('<f', self.data[self.index:self.index + 4])[0]
        self.index += 4
        return val
    
    def string(self, n: int) -> str:
        return self.array(n).decode('latin1')
    
    def find_byte(self, byte: int, start: int) -> int:
        """Find the index of a byte starting from a position"""
        try:
            return self.data.index(byte, start)
        except ValueError:
            return -1


class DracoBitstream:
    """Draco bitstream decoder for compressed mesh data"""
    
    # Constants
    TRIANGULAR_MESH = 1
    MESH_SEQUENTIAL_ENCODING = 0
    SEQUENTIAL_UNCOMPRESSED_INDICES = 1
    
    SEQUENTIAL_ATTRIBUTE_ENCODER_GENERIC = 0
    SEQUENTIAL_ATTRIBUTE_ENCODER_INTEGER = 1
    SEQUENTIAL_ATTRIBUTE_ENCODER_QUANTIZATION = 2
    SEQUENTIAL_ATTRIBUTE_ENCODER_NORMALS = 3
    
    PREDICTION_NONE = -2
    PREDICTION_DIFFERENCE = 0
    
    PREDICTION_TRANSFORM_DELTA = 0
    PREDICTION_TRANSFORM_WRAP = 1
    PREDICTION_TRANSFORM_NORMAL_OCTAHEDRON_CANONICALIZED = 3
    
    @staticmethod
    def leb128(stream: ByteReader) -> int:
        """Decode LEB128 (Little Endian Base 128) variable-length integer"""
        result = 0
        shift = 0
        while True:
            value = stream.uint8()
            result |= (value & 0x7F) << shift
            shift += 7
            if not (value & 0x80):
                break
        return result
    
    @staticmethod
    def parse(stream: ByteReader) -> dict:
        """Parse Draco compressed mesh data"""
        parser = {}
        
        # Parse header
        magic = stream.string(5)
        if magic != "DRACO":
            raise ValueError("Invalid Draco bitstream")
        
        major_version = stream.uint8()
        minor_version = stream.uint8()
        encoder_type = stream.uint8()
        encoder_method = stream.uint8()
        flags = stream.uint16_le()
        
        print(f"DRACO {major_version}.{minor_version} | encoderType: {encoder_type}, encoderMethod: {encoder_method}")
        
        if encoder_type != DracoBitstream.TRIANGULAR_MESH:
            raise NotImplementedError("Only triangular mesh encoding supported")
        
        if flags & 0x8000:  # METADATA_FLAG_MASK
            raise NotImplementedError("Metadata not supported")
        
        # Decode connectivity
        DracoBitstream._decode_connectivity(stream, parser, encoder_method)
        
        # Decode attributes
        DracoBitstream._decode_attribute_data(stream, parser, encoder_method)
        
        # Generate sequence
        DracoBitstream._generate_sequence(parser, encoder_method)
        
        # Decode attributes
        DracoBitstream._decode_attributes(stream, parser)
        
        parser['attributes'] = parser['decoders'][-1]['attributes']
        
        return parser
    
    @staticmethod
    def _decode_connectivity(stream: ByteReader, parser: dict, encoder_method: int):
        """Decode mesh connectivity (faces)"""
        if encoder_method == DracoBitstream.MESH_SEQUENTIAL_ENCODING:
            num_faces = DracoBitstream.leb128(stream)
            num_points = DracoBitstream.leb128(stream)
            connectivity_method = stream.uint8()
            
            parser['numFaces'] = num_faces
            parser['numPoints'] = num_points
            
            faces = []
            
            if connectivity_method == DracoBitstream.SEQUENTIAL_UNCOMPRESSED_INDICES:
                if num_points < 256:
                    for _ in range(num_faces):
                        faces.extend([stream.uint8(), stream.uint8(), stream.uint8()])
                elif num_points < (1 << 16):
                    for _ in range(num_faces):
                        faces.extend([stream.uint16_le(), stream.uint16_le(), stream.uint16_le()])
                elif num_points < (1 << 21):
                    for _ in range(num_faces):
                        faces.extend([DracoBitstream.leb128(stream), 
                                    DracoBitstream.leb128(stream), 
                                    DracoBitstream.leb128(stream)])
                else:
                    for _ in range(num_faces):
                        faces.extend([stream.uint32_le(), stream.uint32_le(), stream.uint32_le()])
            else:
                raise NotImplementedError("Compressed indices not supported")
            
            parser['faces'] = faces
        else:
            raise NotImplementedError("Only sequential encoding supported")
    
    @staticmethod
    def _decode_attribute_data(stream: ByteReader, parser: dict, encoder_method: int):
        """Decode attribute metadata"""
        num_decoders = stream.uint8()
        decoders = []
        
        for i in range(num_decoders):
            decoders.append({
                'attributes': None,
                'pointIds': None,
                'index': i
            })
        
        for decoder in decoders:
            num_attributes = DracoBitstream.leb128(stream)
            attributes = []
            
            for _ in range(num_attributes):
                attributes.append({
                    'attributeType': stream.uint8(),
                    'dataType': stream.uint8(),
                    'numComponents': stream.uint8(),
                    'normalized': stream.uint8(),
                    'uniqueId': DracoBitstream.leb128(stream),
                    'decoderType': None
                })
            
            for attr in attributes:
                attr['decoderType'] = stream.uint8()
            
            decoder['attributes'] = attributes
        
        parser['decoders'] = decoders
    
    @staticmethod
    def _generate_sequence(parser: dict, encoder_method: int):
        """Generate point ID sequence"""
        if encoder_method == DracoBitstream.MESH_SEQUENTIAL_ENCODING:
            for decoder in parser['decoders']:
                decoder['pointIds'] = list(range(parser['numPoints']))
        else:
            raise NotImplementedError("Only sequential encoding supported")
    
    @staticmethod
    def _decode_attributes(stream: ByteReader, parser: dict):
        """Decode attribute values"""
        # Initialize RANS decoder
        rans = DracoBitstream._create_rans()
        parser['rans'] = rans
        parser['bits_value'] = 0
        parser['bits_length'] = 0
        
        for decoder in parser['decoders']:
            for attribute in decoder['attributes']:
                decoder_type = attribute['decoderType']
                
                if decoder_type == DracoBitstream.SEQUENTIAL_ATTRIBUTE_ENCODER_GENERIC:
                    DracoBitstream._decode_attribute_generic(stream, parser, decoder, attribute)
                else:
                    DracoBitstream._decode_attribute_compressed(stream, parser, decoder, attribute, decoder_type)
            
            # Transform attributes
            for attribute in decoder['attributes']:
                decoder_type = attribute['decoderType']
                
                if decoder_type == DracoBitstream.SEQUENTIAL_ATTRIBUTE_ENCODER_QUANTIZATION:
                    DracoBitstream._decode_and_transform_quantized(stream, parser, decoder, attribute)
                elif decoder_type == DracoBitstream.SEQUENTIAL_ATTRIBUTE_ENCODER_NORMALS:
                    DracoBitstream._decode_and_transform_normals(stream, parser, decoder, attribute)
                else:
                    DracoBitstream._transform_generic(parser, decoder, attribute)
    
    @staticmethod
    def _decode_attribute_generic(stream: ByteReader, parser: dict, decoder: dict, attribute: dict):
        """Decode generic (uncompressed) attribute"""
        num_entries = len(decoder['pointIds'])
        num_components = attribute['numComponents']
        num_values = num_entries * num_components
        
        output = []
        data_type = attribute['dataType']
        
        # Data type sizes: 1=INT8, 2=UINT8, 3=INT16, 4=UINT16, 5=INT32, 6=UINT32, 9=FLOAT32
        if data_type in [1, 2]:  # 1 byte
            for _ in range(num_values):
                output.append(stream.uint8())
        elif data_type in [3, 4]:  # 2 bytes
            for _ in range(num_values):
                output.append(stream.uint16_le())
        elif data_type in [5, 6, 9]:  # 4 bytes
            for _ in range(num_values):
                output.append(stream.uint32_le())
        else:
            raise NotImplementedError(f"Data type {data_type} not implemented")
        
        attribute['output'] = output
    
    @staticmethod
    def _decode_attribute_compressed(stream: ByteReader, parser: dict, decoder: dict, attribute: dict, decoder_type: int):
        """Decode compressed attribute with prediction"""
        num_entries = len(decoder['pointIds'])
        num_components = attribute['numComponents']
        num_values = num_entries * num_components
        
        # Read prediction scheme
        prediction_scheme = stream.uint8()
        if prediction_scheme < 0:
            prediction_scheme = prediction_scheme + 256  # Handle signed byte
        if prediction_scheme >= 128:
            prediction_scheme = prediction_scheme - 256
        
        # Read prediction transform
        prediction_transform = stream.uint8()
        if prediction_transform >= 128:
            prediction_transform = prediction_transform - 256
        
        if decoder_type == DracoBitstream.SEQUENTIAL_ATTRIBUTE_ENCODER_INTEGER:
            # Simple integer encoding
            output = DracoBitstream._decode_symbols(stream, parser, num_values)
            attribute['output'] = output
            
            # Apply prediction
            if prediction_scheme == DracoBitstream.PREDICTION_DIFFERENCE:
                DracoBitstream._apply_prediction_difference(attribute, num_components, num_entries)
        else:
            # For other encoder types, use simplified decoding
            output = DracoBitstream._decode_symbols(stream, parser, num_values)
            attribute['output'] = output
            
            if prediction_scheme == DracoBitstream.PREDICTION_DIFFERENCE:
                DracoBitstream._apply_prediction_difference(attribute, num_components, num_entries)
    
    @staticmethod
    def _decode_symbols(stream: ByteReader, parser: dict, num_values: int) -> List[int]:
        """Decode symbols using RANS"""
        rans = parser['rans']
        
        # Read bit length
        bit_length = stream.uint8()
        
        # Initialize RANS for symbols
        rans.init_symbols(stream, bit_length)
        
        # Decode values
        output = []
        for _ in range(num_values):
            output.append(rans.read_symbol())
        
        return output
    
    @staticmethod
    def _apply_prediction_difference(attribute: dict, num_components: int, num_entries: int):
        """Apply differential prediction to decode values"""
        output = attribute['output']
        
        for i in range(num_components, len(output)):
            output[i] = (output[i] + output[i - num_components]) & 0xFFFFFFFF
    
    @staticmethod
    def _decode_and_transform_quantized(stream: ByteReader, parser: dict, decoder: dict, attribute: dict):
        """Decode and dequantize attribute values"""
        num_components = attribute['numComponents']
        output = attribute['output']
        
        # Read quantization parameters
        min_values = [stream.float_le() for _ in range(num_components)]
        range_val = stream.float_le()
        quantization_bits = stream.uint8()
        
        max_quantized = (1 << quantization_bits) - 1
        delta = range_val / max_quantized
        
        # Dequantize
        for i in range(0, len(output), num_components):
            for j in range(num_components):
                output[i + j] = min_values[j] + output[i + j] * delta
    
    @staticmethod
    def _decode_and_transform_normals(stream: ByteReader, parser: dict, decoder: dict, attribute: dict):
        """Decode and transform octahedron-encoded normals"""
        input_data = attribute['output']
        quantization_bits = stream.uint8()
        
        max_value = (1 << quantization_bits) - 2
        dequantization_scale = 2.0 / max_value
        
        output = []
        for i in range(0, len(input_data), 2):
            s = input_data[i]
            t = input_data[i + 1]
            
            y = s * dequantization_scale - 1.0
            z = t * dequantization_scale - 1.0
            x = 1.0 - abs(y) - abs(z)
            
            x_offset = max(0, -x)
            y += x_offset if y < 0 else -x_offset
            z += x_offset if z < 0 else -x_offset
            
            norm_squared = x*x + y*y + z*z
            
            if norm_squared < 1e-6:
                output.extend([0, 0, 0])
            else:
                d = 1.0 / math.sqrt(norm_squared)
                output.extend([x * d, y * d, z * d])
        
        attribute['output'] = output
    
    @staticmethod
    def _transform_generic(parser: dict, decoder: dict, attribute: dict):
        """Transform generic attributes (convert uint32 to float)"""
        output = attribute['output']
        data_type = attribute['dataType']
        
        if data_type == 9:  # FLOAT32
            for i in range(len(output)):
                # Convert uint32 bits to float
                output[i] = struct.unpack('f', struct.pack('I', output[i]))[0]
    
    @staticmethod
    def _create_rans():
        """Create RANS decoder object"""
        return RANSDecoder()


class RANSDecoder:
    """rANS (range Asymmetric Numeral Systems) decoder"""
    
    def __init__(self):
        self.probability_table = []
        self.lookup_table = []
        self.buffer = None
        self.start_index = 0
        self.offset = 0
        self.state = 0
        self.base = 0
        self.precision = 0
        self.prob_zero = 0
    
    def decode_tables(self, stream: ByteReader, expected_cum_prob: int):
        """Decode probability tables"""
        num_symbols = DracoBitstream.leb128(stream)
        
        self.probability_table = []
        self.lookup_table = [0] * expected_cum_prob
        
        cum_prob = 0
        act_prob = 0
        
        i = 0
        while i < num_symbols:
            data = stream.uint8()
            token = data & 3
            
            if token == 3:
                offset = data >> 2
                for j in range(offset + 1):
                    self.probability_table.append({'prob': 0, 'cum_prob': cum_prob})
                i += offset
            else:
                prob = data >> 2
                for j in range(token):
                    eb = stream.uint8()
                    prob |= eb << (8 * (j + 1) - 2)
                
                self.probability_table.append({'prob': prob, 'cum_prob': cum_prob})
                cum_prob += prob
                
                for j in range(act_prob, cum_prob):
                    self.lookup_table[j] = i
                
                act_prob = cum_prob
            
            i += 1
        
        if cum_prob != expected_cum_prob:
            raise ValueError(f"Probability mismatch: {cum_prob} != {expected_cum_prob}")
    
    def _start(self, buffer: bytes, start_index: int, offset: int, base: int, precision: int):
        """Initialize RANS state"""
        self.buffer = buffer
        self.start_index = start_index
        self.base = base
        self.precision = precision
        
        x = buffer[start_index + offset - 1] >> 6
        
        if x == 0:
            self.offset = offset - 1
            self.state = buffer[start_index + offset - 1] & 0x3F
        elif x == 1:
            self.offset = offset - 2
            self.state = ((buffer[start_index + offset - 1] << 8) | 
                         buffer[start_index + offset - 2]) & 0x3FFF
        elif x == 2:
            self.offset = offset - 3
            self.state = ((buffer[start_index + offset - 1] << 16) |
                         (buffer[start_index + offset - 2] << 8) |
                         buffer[start_index + offset - 3]) & 0x3FFFFF
        elif x == 3:
            self.offset = offset - 4
            self.state = ((buffer[start_index + offset - 1] << 24) |
                         (buffer[start_index + offset - 2] << 16) |
                         (buffer[start_index + offset - 3] << 8) |
                         buffer[start_index + offset - 4]) & 0x3FFFFFFF
        
        self.state += base
    
    def read_symbol(self) -> int:
        """Read next symbol"""
        while self.state < self.base and self.offset > 0:
            self.state = (self.state << 8) | self.buffer[self.start_index + self.offset - 1]
            self.offset -= 1
        
        quo = self.state // self.precision
        rem = self.state % self.precision
        
        symbol = self.lookup_table[rem]
        entry = self.probability_table[symbol]
        prob = entry['prob']
        cum_prob = entry['cum_prob']
        
        self.state = quo * prob + rem - cum_prob
        return symbol
    
    def init_symbols(self, stream: ByteReader, bit_length: int):
        """Initialize for symbol decoding"""
        precision_bits = (3 * bit_length) // 2
        precision_bits = max(12, min(20, precision_bits))
        
        precision = 1 << precision_bits
        base = precision * 4
        
        self.decode_tables(stream, precision)
        
        data_size = DracoBitstream.leb128(stream)
        buffer = stream.array(data_size)
        
        self._start(buffer, 0, data_size, base, precision)


class RobloxMeshParser:
    """Parser for Roblox mesh files (versions 1.00 - 7.00)"""
    
    @staticmethod
    def parse(data: bytes) -> dict:
        """Parse a Roblox mesh file"""
        reader = ByteReader(data)
        
        # Check header
        header = reader.string(8)
        if header != "version ":
            raise ValueError("Invalid mesh file")
        
        version = reader.string(4)
        print(f"Mesh version: {version}")
        
        if version in ["1.00", "1.01"]:
            return RobloxMeshParser._parse_text(data.decode('latin1'))
        elif version in ["2.00", "3.00", "3.01", "4.00", "4.01", "5.00"]:
            return RobloxMeshParser._parse_bin(data, version)
        elif version in ["6.00", "7.00"]:
            return RobloxMeshParser._parse_chunked(data, version)
        else:
            raise ValueError(f"Unsupported mesh version: {version}")
    
    @staticmethod
    def _parse_text(text: str) -> dict:
        """Parse text-format mesh (v1.00, v1.01)"""
        lines = text.split('\n')
        if len(lines) < 3:
            raise ValueError("Invalid mesh v1 file")
        
        version = lines[0].strip()
        face_count = int(lines[1].strip())
        data_line = lines[2].strip()
        
        # Parse vectors
        vectors_str = data_line[1:-1]  # Remove [ ]
        vectors = []
        for vec in vectors_str.split(']['):
            values = [float(x) for x in vec.split(',')]
            vectors.append(values)
        
        if len(vectors) != face_count * 9:
            raise ValueError("Length mismatch")
        
        scale_multiplier = 0.5 if version == "version 1.00" else 1.0
        vertex_count = face_count * 3
        
        vertices = []
        normals = []
        uvs = []
        faces = []
        
        for i in range(vertex_count):
            n = i * 3
            vertex = vectors[n]
            normal = vectors[n + 1]
            uv = vectors[n + 2]
            
            vertices.extend([v * scale_multiplier for v in vertex])
            normals.extend(normal)
            uvs.extend(uv[:2])
            faces.append(i)
        
        return {
            'vertices': vertices,
            'normals': normals,
            'uvs': uvs,
            'faces': faces,
            'lods': [0, face_count]
        }
    
    @staticmethod
    def _parse_bin(data: bytes, version: str) -> dict:
        """Parse binary mesh (v2.00 - v5.00)"""
        reader = ByteReader(data)
        
        # Verify header
        header = reader.string(12)
        if header != f"version {version}":
            raise ValueError("Bad header")
        
        # Check newline
        newline = reader.uint8()
        if newline == 0x0D:
            reader.uint8()  # Skip LF
        elif newline != 0x0A:
            raise ValueError("Bad newline")
        
        begin = reader.get_index()
        
        # Parse header based on version
        if version == "2.00":
            header_size = reader.uint16_le()
            if header_size < 12:
                raise ValueError(f"Invalid header size {header_size}")
            
            vertex_size = reader.uint8()
            face_size = reader.uint8()
            vertex_count = reader.uint32_le()
            face_count = reader.uint32_le()
            
            lod_size = 4
            lod_count = 0
            bone_count = 0
            name_table_size = 0
            
        elif version.startswith("3."):
            header_size = reader.uint16_le()
            if header_size < 16:
                raise ValueError(f"Invalid header size {header_size}")
            
            vertex_size = reader.uint8()
            face_size = reader.uint8()
            lod_size = reader.uint16_le()
            lod_count = reader.uint16_le()
            vertex_count = reader.uint32_le()
            face_count = reader.uint32_le()
            
            bone_count = 0
            name_table_size = 0
            
        elif version.startswith("4.") or version.startswith("5."):
            header_size = reader.uint16_le()
            min_header = 24 if version.startswith("4.") else 32
            if header_size < min_header:
                raise ValueError(f"Invalid header size {header_size}")
            
            reader.jump(2)  # lodType
            vertex_count = reader.uint32_le()
            face_count = reader.uint32_le()
            lod_count = reader.uint16_le()
            bone_count = reader.uint16_le()
            name_table_size = reader.uint32_le()
            reader.jump(4)  # subsetCount + numHighQualityLODs + unused
            
            if version.startswith("5."):
                reader.jump(8)  # facsDataFormat + facsDataSize
            
            vertex_size = 40
            face_size = 12
            lod_size = 4
        
        reader.set_index(begin + header_size)
        
        # Read vertices
        vertices = []
        normals = []
        uvs = []
        
        for _ in range(vertex_count):
            # Position
            vertices.extend([reader.float_le(), reader.float_le(), reader.float_le()])
            
            # Normal
            normals.extend([reader.float_le(), reader.float_le(), reader.float_le()])
            
            # UV
            u = reader.float_le()
            v = 1.0 - reader.float_le()  # Flip V
            uvs.extend([u, v])
            
            # Tangent (4 bytes)
            reader.jump(4)
            
            # Color (if present)
            if vertex_size >= 40:
                reader.jump(4)
            
            # Skip remaining
            reader.jump(vertex_size - 36 if vertex_size < 40 else vertex_size - 40)
        
        # Skip bone envelope data
        if bone_count > 0:
            reader.jump(vertex_count * 8)
        
        # Read faces
        faces = []
        for _ in range(face_count):
            faces.extend([reader.uint32_le(), reader.uint32_le(), reader.uint32_le()])
            reader.jump(face_size - 12)
        
        # Read LODs
        lods = []
        if lod_count <= 2:
            lods = [0, face_count]
            reader.jump(lod_count * lod_size)
        else:
            for _ in range(lod_count):
                lods.append(reader.uint32_le())
                reader.jump(lod_size - 4)
        
        return {
            'vertices': vertices,
            'normals': normals,
            'uvs': uvs,
            'faces': faces,
            'lods': lods
        }
    
    @staticmethod
    def _parse_chunked(data: bytes, version: str) -> dict:
        """Parse chunked mesh (v6.00, v7.00) with Draco support"""
        reader = ByteReader(data)
        
        # Verify header
        header = reader.string(12)
        if header != f"version {version}":
            raise ValueError("Bad header")
        
        # Check newline
        newline = reader.uint8()
        if newline == 0x0D:
            reader.uint8()
        elif newline != 0x0A:
            raise ValueError("Bad newline")
        
        mesh = {}
        
        # Read chunks
        while reader.get_remaining() >= 16:
            chunk_type = reader.string(8)
            chunk_version = reader.uint32_le()
            chunk_size = reader.uint32_le()
            chunk_data = reader.array(chunk_size)
            
            if chunk_type == "COREMESH":
                RobloxMeshParser._parse_coremesh_chunk(chunk_data, chunk_version, mesh)
            elif chunk_type == "LODS\x00\x00\x00\x00":
                RobloxMeshParser._parse_lods_chunk(chunk_data, chunk_version, mesh)
        
        return mesh
    
    @staticmethod
    def _parse_coremesh_chunk(data: bytes, version: int, mesh: dict):
        """Parse COREMESH chunk"""
        chunk = ByteReader(data)
        
        if version == 1:
            # Uncompressed format
            num_verts = chunk.uint32_le()
            
            vertices = []
            normals = []
            uvs = []
            
            for _ in range(num_verts):
                vertices.extend([chunk.float_le(), chunk.float_le(), chunk.float_le()])
                normals.extend([chunk.float_le(), chunk.float_le(), chunk.float_le()])
                
                u = chunk.float_le()
                v = 1.0 - chunk.float_le()
                uvs.extend([u, v])
                
                # Tangent + color
                chunk.jump(8)
            
            num_faces = chunk.uint32_le()
            faces = []
            for _ in range(num_faces):
                faces.extend([chunk.uint32_le(), chunk.uint32_le(), chunk.uint32_le()])
            
            mesh['vertices'] = vertices
            mesh['normals'] = normals
            mesh['uvs'] = uvs
            mesh['faces'] = faces
            
            if 'lods' not in mesh:
                mesh['lods'] = [0, num_faces]
                
        elif version == 2:
            # Draco compressed format
            bitstream_size = chunk.uint32_le()
            stream_data = chunk.array(bitstream_size)
            stream = ByteReader(stream_data)
            
            # Parse Draco bitstream
            draco_data = DracoBitstream.parse(stream)
            
            # Extract attributes
            for attribute in draco_data['attributes']:
                unique_id = attribute['uniqueId']
                output = attribute['output']
                
                if unique_id == 0:  # Position
                    mesh['vertices'] = output
                elif unique_id == 1:  # Normals
                    mesh['normals'] = output
                elif unique_id == 2:  # UVs
                    uvs = output[:]
                    # Flip V coordinate
                    for i in range(1, len(uvs), 2):
                        uvs[i] = 1.0 - uvs[i]
                    mesh['uvs'] = uvs
            
            mesh['faces'] = draco_data['faces']
            
            if 'lods' not in mesh:
                mesh['lods'] = [0, len(draco_data['faces']) // 3]
        else:
            raise ValueError(f"Unknown COREMESH version {version}")
    
    @staticmethod
    def _parse_lods_chunk(data: bytes, version: int, mesh: dict):
        """Parse LODS chunk"""
        chunk = ByteReader(data)
        
        if version == 1:
            chunk.jump(3)  # lodType, numHighQualityLODs
            num_lods = chunk.uint32_le()
            
            if num_lods <= 2:
                chunk.jump(num_lods * 4)
            else:
                lods = []
                for _ in range(num_lods):
                    lods.append(chunk.uint32_le())
                mesh['lods'] = lods
        else:
            raise ValueError(f"Unknown LODS version {version}")


def merge_by_distance(vertices: List[float], normals: List[float], uvs: List[float], 
                     faces: List[int], distance: float = 0.0001) -> Tuple[List[float], List[float], List[float], List[int]]:
    """
    Merge vertices that are within a certain distance of each other.
    Similar to Blender's Merge by Distance feature.
    """
    num_verts = len(vertices) // 3
    
    if distance <= 0:
        return vertices, normals, uvs, faces
    
    print(f"Merging vertices within distance {distance}...")
    
    # Build vertex mapping
    vertex_map = {}  # old_index -> new_index
    new_vertices = []
    new_normals = []
    new_uvs = []
    
    distance_sq = distance * distance
    
    for i in range(num_verts):
        vi = i * 3
        ui = i * 2
        
        v_pos = (vertices[vi], vertices[vi + 1], vertices[vi + 2])
        v_normal = (normals[vi], normals[vi + 1], normals[vi + 2])
        v_uv = (uvs[ui], uvs[ui + 1])
        
        # Check if this vertex is close to any existing vertex
        found = False
        for new_idx in range(len(new_vertices) // 3):
            nvi = new_idx * 3
            nui = new_idx * 2
            
            # Calculate distance
            dx = vertices[vi] - new_vertices[nvi]
            dy = vertices[vi + 1] - new_vertices[nvi + 1]
            dz = vertices[vi + 2] - new_vertices[nvi + 2]
            dist_sq = dx*dx + dy*dy + dz*dz
            
            if dist_sq <= distance_sq:
                # Also check if normals and UVs are similar
                dn_x = normals[vi] - new_normals[nvi]
                dn_y = normals[vi + 1] - new_normals[nvi + 1]
                dn_z = normals[vi + 2] - new_normals[nvi + 2]
                normal_diff = abs(dn_x) + abs(dn_y) + abs(dn_z)
                
                du = uvs[ui] - new_uvs[nui]
                dv = uvs[ui + 1] - new_uvs[nui + 1]
                uv_diff = abs(du) + abs(dv)
                
                # If position, normal and UV are all similar, merge them
                if normal_diff < 0.01 and uv_diff < 0.01:
                    vertex_map[i] = new_idx
                    found = True
                    break
        
        if not found:
            # Add as new vertex
            new_idx = len(new_vertices) // 3
            vertex_map[i] = new_idx
            new_vertices.extend(v_pos)
            new_normals.extend(v_normal)
            new_uvs.extend(v_uv)
    
    # Remap faces
    new_faces = []
    for face_idx in faces:
        new_faces.append(vertex_map[face_idx])
    
    print(f"  Merged {num_verts} vertices down to {len(new_vertices) // 3}")
    
    return new_vertices, new_normals, new_uvs, new_faces


def mesh_to_obj(mesh: dict, output_path: str, texture_path: Optional[str] = None, 
                merge_distance: float = 0.0):
    """Convert parsed mesh to OBJ format"""
    vertices = mesh['vertices']
    normals = mesh['normals']
    uvs = mesh['uvs']
    faces = mesh['faces']
    lods = mesh.get('lods', [0, len(faces) // 3])
    
    # Extract only first LOD faces
    face_start = lods[0] * 3
    face_end = lods[1] * 3
    lod_faces = faces[face_start:face_end]
    
    # Apply merge by distance if requested
    if merge_distance > 0:
        vertices, normals, uvs, lod_faces = merge_by_distance(
            vertices, normals, uvs, lod_faces, merge_distance
        )
    
    lines = []
    
    # Add MTL file reference if texture is provided
    if texture_path:
        mtl_path = output_path.rsplit('.', 1)[0] + '.mtl'
        lines.append(f"mtllib {mtl_path.split('/')[-1]}")
    
    lines.append("o Mesh")
    lines.append("")
    
    # Write vertices
    for i in range(0, len(vertices), 3):
        lines.append(f"v {vertices[i]} {vertices[i+1]} {vertices[i+2]}")
    
    lines.append("")
    
    # Write normals
    for i in range(0, len(normals), 3):
        lines.append(f"vn {normals[i]} {normals[i+1]} {normals[i+2]}")
    
    lines.append("")
    
    # Write UVs
    for i in range(0, len(uvs), 2):
        lines.append(f"vt {uvs[i]} {uvs[i+1]}")
    
    lines.append("")
    
    # Use material if texture is provided
    if texture_path:
        lines.append("usemtl Material")
        lines.append("")
    
    # Write faces
    for i in range(0, len(lod_faces), 3):
        a = lod_faces[i] + 1
        b = lod_faces[i + 1] + 1
        c = lod_faces[i + 2] + 1
        lines.append(f"f {a}/{a}/{a} {b}/{b}/{b} {c}/{c}/{c}")
    
    # Write OBJ file
    with open(output_path, 'w') as f:
        f.write('\n'.join(lines))
    
    # Write MTL file if texture is provided
    if texture_path:
        mtl_path = output_path.rsplit('.', 1)[0] + '.mtl'
        create_mtl_file(mtl_path, texture_path)
    
    print(f"Converted mesh to {output_path}")
    print(f"  Vertices: {len(vertices) // 3}")
    print(f"  Faces: {len(lod_faces) // 3}")
    if texture_path:
        print(f"  Texture: {texture_path}")


def create_mtl_file(mtl_path: str, texture_path: str):
    """Create an MTL (material) file for the OBJ"""
    lines = [
        "# Material file created by Roblox Mesh Converter",
        "",
        "newmtl Material",
        "Ka 1.000 1.000 1.000",  # Ambient color
        "Kd 1.000 1.000 1.000",  # Diffuse color
        "Ks 0.000 0.000 0.000",  # Specular color
        "Ns 10.000",             # Specular exponent
        "d 1.0",                 # Transparency (1.0 = opaque)
        "illum 2",               # Illumination model
    ]
    
    # Add texture map
    lines.append(f"map_Kd {texture_path}")
    
    with open(mtl_path, 'w') as f:
        f.write('\n'.join(lines))
    
    print(f"Created material file: {mtl_path}")


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Convert Roblox .mesh files to .obj format (supports v1.00-7.00)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s mesh.mesh
  %(prog)s mesh.mesh -o output.obj
  %(prog)s mesh.mesh -m 0.001
  %(prog)s mesh.mesh -t texture.png
  %(prog)s mesh.mesh -m 0.0001 -t texture.png -o output.obj
        """
    )
    
    parser.add_argument('input', help='Input .mesh file')
    parser.add_argument('-o', '--output', help='Output .obj file (default: same as input with .obj extension)')
    parser.add_argument('-m', '--merge', type=float, default=0.0, metavar='DISTANCE',
                       help='Merge vertices within this distance (default: 0.0 = disabled), Still currently WIP')
    parser.add_argument('-t', '--texture', help='Texture image path to include in material')
    
    args = parser.parse_args()
    
    input_path = args.input
    output_path = args.output if args.output else input_path.rsplit('.', 1)[0] + '.obj'
    merge_distance = args.merge
    texture_path = args.texture
    
    print(f"Reading {input_path}...")
    with open(input_path, 'rb') as f:
        data = f.read()
    
    print("Parsing mesh...")
    mesh = RobloxMeshParser.parse(data)
    
    print("Converting to OBJ...")
    mesh_to_obj(mesh, output_path, texture_path, merge_distance)
    
    print("Done!")


if __name__ == '__main__':
    main()