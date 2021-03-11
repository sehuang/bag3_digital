# BSD 3-Clause License
#
# Copyright (c) 2018, Regents of the University of California
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
#
# * Neither the name of the copyright holder nor the names of its
#   contributors may be used to endorse or promote products derived from
#   this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

# -*- coding: utf-8 -*-

from typing import Dict, Any, Mapping

import pkg_resources
from pathlib import Path

from bag.design.module import Module
from bag.design.database import ModuleDB
from bag.util.immutable import Param

from pybag.enum import TermType


# noinspection PyPep8Naming
class bag3_digital__des_1toN(Module):
    """Module for library bag3_digital cell des_1toN.

    Fill in high level description here.
    """

    yaml_file = pkg_resources.resource_filename(__name__,
                                                str(Path('netlist_info',
                                                         'des_1toN.yaml')))

    def __init__(self, database: ModuleDB, params: Param, **kwargs: Any) -> None:
        Module.__init__(self, self.yaml_file, database, params, **kwargs)

    @classmethod
    def get_params_info(cls) -> Dict[str, str]:
        """Returns a dictionary from parameter names to descriptions.

        Returns
        -------
        param_info : Optional[Dict[str, str]]
            dictionary from parameter names to descriptions.
        """
        return dict(
            flop_fast='Parameters for flop with fast clock',
            flop_slow='Parameters for flop with divided slow clock',
            inv_fast='Parameters for fast clock inverter',
            inv_slow='Parameters for divided slow clock inverter',
            des_ratio='Number of deserialized outputs',
            export_nets='True to export intermediate nets',
        )

    def design(self, flop_fast: Mapping[str, Any], flop_slow: Mapping[str, Any], inv_fast: Mapping[str, Any],
               inv_slow: Mapping[str, Any], des_ratio: int, export_nets: bool) -> None:

        self.instances['XFF'].design(**flop_fast)
        self.reconnect_instance_terminal('XFF', 'clkb', 'clkb')
        self.instances['XFS'].design(**flop_slow)
        self.reconnect_instance_terminal('XFS', 'clkb', 'clk_divb')

        self.instances['XINVC'].design(**inv_fast)
        self.instances['XINVD'].design(**inv_slow)

        if des_ratio < 2:
            raise ValueError(f'des_ratio={des_ratio} has to be greater than 1.')

        suf = f'<{des_ratio - 1}:0>'
        self.rename_pin('dout', 'dout' + suf)

        fast_list, slow_list = [], []
        for idx in range(des_ratio):
            fast_list.append((f'XFF{idx}', [('out', f'd<{idx}>'), ('in', f'd<{idx - 1}>' if idx else 'din')]))
            slow_list.append((f'XFS{idx}', [('out', f'dout<{idx}>'), ('in', f'd<{idx}>')]))

        self.array_instance('XFF', inst_term_list=fast_list)
        self.array_instance('XFS', inst_term_list=slow_list)

        if export_nets:
            self.add_pin('d' + suf, TermType.output)
            self.add_pin('clkb', TermType.output)
            self.add_pin('clk_divb', TermType.output)