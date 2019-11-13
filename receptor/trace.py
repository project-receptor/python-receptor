import jaeger_client

trace_config = jaeger_client.Config(
    config={
        'sampler': {
            'type': 'const',
            'param': 1,
        },
        'logging': True,
    },
    service_name='receptor',
    validate=True,
)
tracer = trace_config.initialize_tracer()
