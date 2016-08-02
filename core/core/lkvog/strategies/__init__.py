from core.lkvog.strategies.closure import Closure
from core.lkvog.strategies.scotch import Scotch
from core.lkvog.strategies.separate_modules import SeparateModules
from core.lkvog.strategies.manual import Manual
from core.lkvog.strategies.advanced import Advanced

strategies_list = {'separate modules': SeparateModules, 'closure': Closure, 'scotch': Scotch, 'advanced': Advanced,
                   'manual': Manual}
