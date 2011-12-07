# Test fixture!

configured = False

def configure_karl(config):
    global configured
    configured = True

    config.hook_zca()
    config.include('pyramid_zcml')
    config.load_zcml()
