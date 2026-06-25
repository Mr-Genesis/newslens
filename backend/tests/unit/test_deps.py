"""Wave E S0: the Anthropic SDK is installed (provider support depends on it)."""


def test_anthropic_importable():
    import anthropic

    assert hasattr(anthropic, "AsyncAnthropic")
