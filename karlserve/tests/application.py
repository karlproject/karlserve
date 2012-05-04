# Test fixture!

configured = False

def configure_karl(config):
    global configured
    configured = True

    from karl.application import configure_karl as config_core
    config_core(config, load_zcml=False)
    config.hook_zca()
    config.include('bottlecap')
    config.include('pyramid_zcml')
    config.load_zcml()
