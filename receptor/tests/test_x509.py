import datetime
import logging
import pytest
import uuid

from cryptography import x509 as c_x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from freezegun import freeze_time

import receptor
from receptor.config import ReceptorConfig
from receptor.exceptions import ReceptorConfigError, SecurityError
from receptor.security import x509


logger = logging.getLogger(__name__)


def cert_generator(subject, issuer, public_key, signing_key, is_ca, key_cert_sign):
    one_day = datetime.timedelta(days=1)
    builder = c_x509.CertificateBuilder()
    builder = builder.subject_name(subject)
    builder = builder.issuer_name(issuer)
    builder = builder.not_valid_before(datetime.datetime.today() - one_day)
    builder = builder.not_valid_after(datetime.datetime.today() + one_day)
    builder = builder.serial_number(c_x509.random_serial_number())
    builder = builder.public_key(public_key)
    builder = builder.add_extension(
        c_x509.BasicConstraints(ca=is_ca, path_length=None), critical=True
    )
    builder = builder.add_extension(
        c_x509.KeyUsage(digital_signature=False,
                        content_commitment=False,
                        key_encipherment=False,
                        data_encipherment=False,
                        key_agreement=False,
                        key_cert_sign=key_cert_sign,
                        crl_sign=False,
                        encipher_only=False,
                        decipher_only=False), critical=True
    )
    cert = builder.sign(private_key=signing_key, algorithm=hashes.SHA256(),
                        backend=default_backend())
    return cert


@pytest.fixture
def ca():
    node_id = str(uuid.uuid4())
    logger.info('CA node id: %s', node_id)
    distinguished_name = x509.parse_dn(f'/O=receptor/OU=nodes/CN={node_id}')
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    public_key = private_key.public_key()
    cert = cert_generator(distinguished_name, distinguished_name, 
                          public_key, private_key, True, True)
    return dict(node_id=node_id, cert=cert, key=private_key)

@pytest.fixture
def different_ca(tmp_path):
    node_id = str(uuid.uuid4())
    logger.info('CA node id: %s', node_id)
    distinguished_name = x509.parse_dn(f'/O=receptor/OU=nodes/CN={node_id}')
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    public_key = private_key.public_key()
    cert = cert_generator(distinguished_name, distinguished_name, 
                          public_key, private_key, True, True)
    ca_cert_path = tmp_path / 'alt_ca_cert.pem'
    ca_cert_path.write_bytes(
        cert.public_bytes(
            encoding=serialization.Encoding.PEM
        )
    )
    return dict(node_id=node_id, cert=cert, key=private_key, cert_path=ca_cert_path)


@pytest.fixture
def node(ca, tmp_path):
    node_id = str(uuid.uuid4())
    logger.info('Test node id: %s', node_id)
    subject = x509.parse_dn(f'/O=receptor/OU=nodes/CN={node_id}')
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    cert = cert_generator(subject, ca['cert'].subject, private_key.public_key(),
                          ca['key'], False, False)
    
    ca_cert_path = tmp_path / 'ca_cert.pem'
    ca_cert_path.write_bytes(
        ca['cert'].public_bytes(
            encoding=serialization.Encoding.PEM
        )
    )

    node_cert_path = tmp_path / 'cert.pem'
    node_cert_path.write_bytes(
        cert.public_bytes(
            encoding=serialization.Encoding.PEM
        )
    )

    node_key_path = tmp_path / 'key.pem'
    node_key_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        )
    )

    config = ReceptorConfig(cmdline_args=dict(
        x509=dict(
            ca_cert_path=ca_cert_path,
            cert_path=node_cert_path,
            key_path=node_key_path
        )
    ))
    return dict(node_id=node_id, cert=cert, key=private_key, 
                receptor=receptor.Receptor(node_id=node_id,
                                           config=config))


def test_happy_path_config(ca, node):
    csm = x509.CertificateSecurityManager(node['receptor'])
    assert csm.ca_certs == [ca['cert']]
    assert csm.cert == node['cert']
    csm_key_bytes = csm.key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    )
    node_key_bytes = node['key'].private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    )
    assert csm_key_bytes == node_key_bytes


def test_message_signing(node):
    csm = x509.CertificateSecurityManager(node['receptor'])
    message = b'Project Receptor'
    signature = csm.generate_signature(message)
    cert_as_pem = node['cert'].public_bytes(encoding=serialization.Encoding.PEM)
    assert csm.verify_signature(message, signature, cert_as_pem) == node['node_id']


def test_cert_config_sanity_checks(ca, different_ca, node):
    base_x509 = dict(
        ca_cert_path=node['receptor'].config.x509.ca_cert_path,
        cert_path=node['receptor'].config.x509.cert_path,
        key_path=node['receptor'].config.x509.key_path
    )

    # Missing config for ca cert, cert, or key should throw config errors
    for key_to_remove in ['ca_cert_path', 'cert_path', 'key_path']:
        partial_x509 = base_x509.copy()
        del partial_x509[key_to_remove]
        config = ReceptorConfig(cmdline_args=dict(x509=partial_x509))
        receptor_obj = receptor.Receptor(node_id=node['node_id'],
                                         config=config)
        with pytest.raises(ReceptorConfigError, match=r'.*defined in configuration.*'):
            x509.CertificateSecurityManager(receptor_obj)
    
    # Bad path for ca cert, cert, or key should throw config errors
    for key_to_alter in ['ca_cert_path', 'cert_path', 'key_path']:
        altered_x509 = base_x509.copy()
        altered_x509[key_to_alter] += 'x'
        config = ReceptorConfig(cmdline_args=dict(x509=altered_x509))
        receptor_obj = receptor.Receptor(node_id=node['node_id'],
                                         config=config)
        with pytest.raises(ReceptorConfigError, match=r'.*not found or not readable.*'):
            x509.CertificateSecurityManager(receptor_obj)
    
    # Invalid ca cert, cert, or key should throw config errors
    for key_to_alter in ['ca_cert_path', 'cert_path', 'key_path']:
        altered_x509 = base_x509.copy()
        with open(altered_x509[key_to_alter] + 'x', 'w') as ofs:
            with open(altered_x509[key_to_alter]) as ifs:
                ofs.write(ifs.read().replace('-', '='))
        altered_x509[key_to_alter] += 'x'
        config = ReceptorConfig(cmdline_args=dict(x509=altered_x509))
        receptor_obj = receptor.Receptor(node_id=node['node_id'],
                                         config=config)
        with pytest.raises(ReceptorConfigError, match=r'Invalid.*'):
            x509.CertificateSecurityManager(receptor_obj)
    
    # Configured ca_cert or cert out of validity should throw config errors
    one_week_ago = datetime.datetime.utcnow() - datetime.timedelta(days=7)
    one_week_later = datetime.datetime.utcnow() + datetime.timedelta(days=7)
    with freeze_time(str(one_week_ago)):
        with pytest.raises(ReceptorConfigError, match=r'.*valid date range.*'):
            x509.CertificateSecurityManager(receptor_obj)
    with freeze_time(str(one_week_later)):
        with pytest.raises(ReceptorConfigError, match=r'.*valid date range.*'):
            x509.CertificateSecurityManager(receptor_obj)
    # ... unless ignore_cert_dates is set
    altered_x509 = base_x509.copy()
    altered_x509['ignore_cert_dates'] = True
    config = ReceptorConfig(cmdline_args=dict(x509=altered_x509))
    receptor_obj = receptor.Receptor(node_id=node['node_id'],
                                     config=config)
    _ = x509.CertificateSecurityManager(receptor_obj)

    # TODO: Confirm configured CA cert is a signing cert

    # Cert has to be signed by configured CA
    altered_x509 = base_x509.copy()
    altered_x509['ca_cert_path'] = different_ca['cert_path']
    config = ReceptorConfig(cmdline_args=dict(x509=altered_x509))
    receptor_obj = receptor.Receptor(node_id=node['node_id'],
                                     config=config)
    with pytest.raises(ReceptorConfigError, match=r'.*not signed by.*'):
        x509.CertificateSecurityManager(receptor_obj)
    
    # Cert has to match configured node ID
    node_id = str(uuid.uuid4())
    receptor_obj = receptor.Receptor(node_id=node_id, config=node['receptor'].config)
    with pytest.raises(ReceptorConfigError, match=r'.*does not match.*'):
        x509.CertificateSecurityManager(receptor_obj)
    