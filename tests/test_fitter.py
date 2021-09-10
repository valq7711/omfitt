
import pytest
from omfitt import BaseFixture, FixtureService, BaseProcessor, FixtureShop, Fitter
from unittest.mock import MagicMock


class Proc(BaseProcessor):
    def init_context(self):
        pass


class Fixture(BaseFixture):
    def __init__(self, name, raise_=None):
        self.name = name
        if not raise_:
            raise_ = ['', None, None]
        self.raise_ = raise_

    def take_on(self, ctx):
        cb_name, err_cls, stop_final = self.raise_
        self._safe_local = {}
        ctx.shared_data[self.name] = ['touch']
        ctx.shared_data[self.name + '_ph'] = [ctx.phase]
        if cb_name == 'take_on':
            raise err_cls(self.name)

    def on_output(self, ctx):
        cb_name, err_cls, stop_final = self.raise_
        ctx.shared_data[self.name].append('out')
        ctx.shared_data[self.name + '_ph'].append(ctx.phase)
        ctx.output.append(self.name)
        if cb_name == 'on_output':
            raise err_cls(self.name)

    def on_finalize(self, ctx):
        cb_name, err_cls, stop_final = self.raise_
        ctx.shared_data[self.name].append('final')
        ctx.shared_data[self.name + '_ph'].append(ctx.phase)
        if cb_name == 'on_finalize':
            if stop_final:
                ctx.stop_finalize = True
            raise err_cls(self.name)


@pytest.fixture
def foo_bar_baz(request):
    ret = [Fixture(f, r) for f, r in request.param]
    BaseFixture.__init_request_ctx__()
    return ret


@pytest.fixture
def ferr():
    ret = Fixture('ferr', True)
    BaseFixture.__init_request_ctx__()
    return ret


@pytest.fixture
def foo_bar_baz_deps(foo_bar_baz):
    foo_, bar_, baz_ = foo_bar_baz
    bar_.use_fixtures(foo_)
    baz_.use_fixtures(bar_)
    return foo_bar_baz


@pytest.fixture
def shop(foo_bar_baz):
    foo_, bar_, baz_ = foo_bar_baz

    @FixtureShop.make_from
    class Shop:
        foo = foo_
        bar = bar_
        baz = baz_

    return Shop


@pytest.fixture
def fx_service(shop):
    fs = FixtureService(reverse_postproc=False)
    fs.serve(shop)
    return fs


@pytest.fixture
def fx_proc(fx_service):
    return Proc(fx_service, {})


class Mounter:
    def __init__(self):
        self.dict = {}

    def __call__(self, key):
        def inner(f):
            self.dict[key] = f
        return inner


@pytest.fixture
def mounter():
    return Mounter()


@pytest.fixture
def action(fx_proc: Proc, foo_bar_baz, shop, mounter):
    return Fitter(fx_proc, [shop], mounter)


@pytest.fixture
def action_foo(shop, action: Fitter):
    @action('/foo')
    @action.uses(shop.foo, shop.bar)
    def core(arg=None):
        if arg:
            arg('core')
            shop.baz
        return ['a']
    return action


@pytest.fixture
def action_out(action_foo, shop):
    @action_foo('/bar')
    @action_foo.uses(shop.baz)
    def core(arg=None):
        if arg:
            arg('barcore')
            shop.foo
        return ['/bar']
    return action_foo


@pytest.mark.parametrize(
    'arg, foo_bar_baz',
    [
        [
            MagicMock(),
            [('foo', False), ('bar', False), ('baz', False)]
        ],
    ],
    indirect=['foo_bar_baz']
)
def test_action(action_out, mounter, arg: MagicMock):
    action_out.mount()
    assert mounter.dict['/foo']
    res = mounter.dict['/foo'](arg)
    arg.assert_called_with('core')
    assert res == ['a', 'foo', 'bar', 'baz']

    assert mounter.dict['/bar']
    res = mounter.dict['/bar'](arg)
    arg.assert_called_with('barcore')
    assert res == ['/bar', 'baz', 'foo']

