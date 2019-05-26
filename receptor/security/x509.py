import base64
import datetime
import json
import logging
import uuid

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives import serialization, hashes
from cryptography import x509
from cryptography.x509.name import _NAMEOID_TO_NAME
from cryptography import exceptions as cryptography_exceptions

from .base import BaseSecurityManager
from ..exceptions import ReceptorConfigError, SecurityError

logger = logging.getLogger(__name__)


def parse_dn(base_dn):
    attribute_list = []
    oid_reverse_lookup = {v: k for k, v in _NAMEOID_TO_NAME.items()}
    for attribute in base_dn.split('/')[1:]:
        name, value = attribute.split('=', 1)
        attribute_list.append(x509.NameAttribute(oid_reverse_lookup[name], value))
    return x509.Name(attribute_list)


class CertificateSecurityManager(BaseSecurityManager):
    def __init__(self, receptor):
        super().__init__(receptor)
        ca_cert_file = self.receptor.config.x509.ca_cert_path
        # Making this a list right now to support chaining later.
        self.ca_certs = [self.__load_cert__(ca_cert_file, 'CA certificate')]
        self.ignore_cert_dates = self.receptor.config.x509.ignore_cert_dates
        self.ignore_signing_extensions = self.receptor.config.x509.ignore_signing_extensions
        # TODO: Implement with chaining support
        # self.ignore_path_length = self.receptor.config.x509.ignore_path_length

        for ca_cert in self.ca_certs:
            if not (self.ignore_cert_dates or self.test_certificate_dates(ca_cert)):
                raise ReceptorConfigError('CA cert in %s is outside of its valid date range', ca_cert_file)
            if not (self.ignore_signing_extensions or self.test_can_sign_certs(ca_cert)):
                raise ReceptorConfigError('CA cert in %s is not a signing cert', ca_cert_file)
        
        cert_file = self.receptor.config.x509.cert_path
        self.cert = self.__load_cert__(cert_file)
        key_file = self.receptor.config.x509.key_path
        self.key = self.__load_key__(key_file)

        try:
            self.verify_chain_of_trust(self.cert)
        except SecurityError:
            raise ReceptorConfigError('Configured certificate not signed by configured CA.')
        
        self.base_dn = parse_dn(self.receptor.config.x509.base_dn)
        if not self.get_node_id_from_cert(self.cert) == self.receptor.node_id:
            raise ReceptorConfigError('Configured certificate does not match node ID')

    
    def __load_cert__(self, cert_path, description='host certificate'):
        try:
            with open(cert_path, 'rb') as ifs:
                cert_obj = x509.load_pem_x509_certificate(ifs.read(), default_backend())
        except TypeError as e:
            logger.debug(f'Original exception: {e}')
            raise ReceptorConfigError(f'No {description} defined in configuration.')
        except OSError as e:
            logger.debug(f'Original exception: {e}')
            raise ReceptorConfigError(f'The {description} {cert_path} not found or not readable.')
        except ValueError as e:
            logger.debug(f'Original exception: {e}')
            raise ReceptorConfigError(f'Invalid {description} defined in configuration.')
        return cert_obj
    
    def __load_key__(self, key_path):
        try:
            with open(key_path, 'rb') as ifs:
                key_obj = serialization.load_pem_private_key(
                    ifs.read(),
                    password=None,
                    backend=default_backend()
                )
        except TypeError as e:
            logger.debug(f'Original exception: {e}')
            raise ReceptorConfigError(f'No private key defined in configuration.')
        except OSError as e:
            logger.debug(f'Original exception: {e}')
            raise ReceptorConfigError(f'The private key {key_path} not found or not readable.')
        except ValueError as e:
            logger.debug(f'Original exception: {e}')
            raise ReceptorConfigError('Invalid private key defined in configuration.')
        return key_obj
        
    # BaseSecurityManager interface implementation


    async def verify_node(self, node):
        return True

    async def verify_controller(self, controller):
        return True

    async def verify_msg(self, msg):
        msg_obj = json.loads(msg)
        signing_node = self.verify_signature(msg_obj['m'], msg_obj['s'], msg_obj['c'])
        decoded_msg = json.loads(msg_obj['message'])
        if decoded_msg['sender'] != signing_node:
            raise SecurityError('Message signer was %s but sender was %s', 
                                signing_node, decoded_msg['sender'])
        return decoded_msg

    async def verify_directive(self, directive):
        return True

    async def verify_response(self, response):
        return True
    
    async def sign_response(self, inner_envelope):
        message = json.dumps(
            {attr: getattr(inner_envelope, attr)
             for attr in ['message_id', 'sender', 'recipient', 'message_type',
                          'timestamp', 'raw_payload', 'directive',
                          'in_response_to', 'ttl', 'serial']}
        ).encode('utf8')
        signature = base64.encodebytes(self.generate_signature(message))
        cert_pem = self.cert.public_bytes(encoding=serialization.Encoding.PEM)
        return json.dumps(dict(m=message, s=signature, c=cert_pem))


    # x509 implementation
    # Largely inspired by https://github.com/openstack/cursive
    # 
    # Used with permission under Apache License, version 2


    def test_certificate_dates(self, cert_obj):
        now = datetime.datetime.utcnow()
        return cert_obj.not_valid_before < now < cert_obj.not_valid_after
    
    def test_issued_by_ca(self, ca_cert, cert_obj):
        return ca_cert.subject == cert_obj.issuer and \
            self.verify_cert_signature(ca_cert, cert_obj)
    
    def test_can_sign_certs(self, cert_obj):
        try:
            basic_constraints = cert_obj.extensions.get_extension_for_oid(
                x509.oid.ExtensionOID.BASIC_CONSTRAINTS
            ).value
        except x509.extensions.ExtensionNotFound:
            logger.debug('Certificate has no basic constraints extension')
            return False
        
        try:
            key_usage = cert_obj.extensions.get_extension_for_oid(
                x509.oid.ExtensionOID.KEY_USAGE
            ).value
        except x509.extensions.ExtensionNotFound:
            logger.debug('Certificate has no key usage extension')
            return False
        
        if not basic_constraints.ca:
            logger.debug('Certificate is not a CA cert.')
            return False
        
        if not key_usage.key_cert_sign:
            logger.debug('Certificate is not for verifying certificate signatures.')
            return False
        
        return True

    def verify_cert_signature(self, ca_cert, cert_obj):
        try:
            if isinstance(ca_cert.public_key(), rsa.RSAPublicKey):
                ca_cert.public_key().verify(
                    cert_obj.signature, cert_obj.tbs_certificate_bytes, 
                    padding.PKCS1v15(), cert_obj.signature_hash_algorithm
                )
            elif isinstance(ca_cert.public_key(), ec.EllipticCurvePublicKey):
                ca_cert.public_key().verify(
                    cert_obj.signature, cert_obj.tbs_certificate_bytes, 
                    ec.ECDSA(cert_obj.signature_hash_algorithm)
                )
            else:
                ca_cert.public_key().verify(
                    cert_obj.tbs_certificate_bytes, 
                    cert_obj.signature_hash_algorithm
                )

        except cryptography_exceptions.InvalidSignature as e:
            logger.error('Certificate verification failed: %s', e)
            return False
        else:
            return True
    
    def verify_chain_of_trust(self, cert_obj):
        if not (self.ignore_cert_dates or self.test_certificate_dates(cert_obj)):
            raise SecurityError('Certificate %s is outside of its valid date range', cert_obj)

        # TODO: Implement chain verification
        ca_cert = self.ca_certs[0]
        if not self.test_issued_by_ca(ca_cert, cert_obj):
            raise SecurityError('Certificate %s does not have valid '
                                'signature from %s', cert_obj, ca_cert)
    
    def get_node_id_from_cert(self, cert_obj):
        subject = cert_obj.subject
        
        # Ensure the subject is in the base DN
        if not all(map(lambda tpl: tpl[0] == tpl[1], zip(subject, self.base_dn))):
            raise SecurityError('Certificate subject does not match the base DN')

        cn_attrs = subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)
        if not cn_attrs:
            raise SecurityError('Certificate does not have a node identifier.')
        cn = cn_attrs[0].value
        try:
            node_id = uuid.UUID(cn)
        except ValueError:
            raise SecurityError('Certificate subject is not a valid node identifier.')
        return str(node_id)
    
    def verify_signature(self, message, signature, cert_pem):
        try:
            cert_obj = x509.load_pem_x509_certificate(cert_pem, default_backend())
        except ValueError:
            raise SecurityError('Invalid certificate provided.')
        self.verify_chain_of_trust(cert_obj)
        public_key = cert_obj.public_key()
        try:
            public_key.verify(
                signature,
                message,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
        except cryptography_exceptions.InvalidSignature:
            raise SecurityError('Message signature verification failed!')
        return self.get_node_id_from_cert(cert_obj)
    
    def generate_signature(self, message):
        return self.key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )


class CSRGenerator:
    def __init__(self, receptor, controller=False):
        self.receptor = receptor
        self.controller = controller
    
    def generate_private_key(self, ofs):
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=4096,
            backend=default_backend()
        )
        ofs.write(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            )
        )
        return private_key
    
    def generate_csr(self, key, ofs):
        csr = x509.CertificateSigningRequestBuilder()
        csr = csr.subject_name(
            parse_dn(f'{self.receptor.config.x509.base_dn}/CN={self.receptor.node_id}')
        )   
        csr = csr.add_extension(
            x509.BasicConstraints(ca=False, path_length=None), critical=True
        )
        csr = csr.add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=self.controller,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False
            ), critical=True
        )
        csr = csr.sign(key, hashes.SHA256(), default_backend())
        ofs.write(csr.public_bytes(serialization.Encoding.PEM))


        

    

        