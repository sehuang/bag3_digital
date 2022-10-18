from cProfile import label
from typing import Any, Mapping, Optional, Type

from bag.util.immutable import Param
from bag.design.module import Module
from bag.layout.template import TemplateDB

from xbase.layout.mos.base import MOSBasePlaceInfo, MOSBase

from .inv_diff import InvDiffCore
from ...schematic.inv_diff_chain import bag3_digital__inv_diff_chain


class InvDiffChain(MOSBase):
    """Differential inverter cell chain using inverters"""
    def __init__(self, temp_db: TemplateDB, params: Param, **kwargs: Any) -> None:
        MOSBase.__init__(self, temp_db, params, **kwargs)

    @classmethod
    def get_schematic_class(cls) -> Optional[Type[Module]]:
        return bag3_digital__inv_diff_chain

    @classmethod
    def get_params_info(cls) -> Mapping[str, str]:
        return dict(
            pinfo='The MOSBasePlaceInfo object.',
            seg_drv='number of segments of inverter.',
            seg_kp='number of segments of keeper.',
            w_p='pmos width.',
            w_n='nmos width.',
            ridx_p='pmos row index.',
            ridx_n='nmos row index.',
            sig_locs='Signal track location dictionary.',
            length='Length of the chain',
            export_nodes='True to label nodes; False by default.',
            vertical_in='True to have inputs on vertical layer; False by default',
            sep_vert_in='True to use separate vertical tracks for in and inb; False by default',
            sep_vert_out='True to use separate vertical tracks for out and outb; False by default',
        )

    @classmethod
    def get_default_param_values(cls) -> Mapping[str, Any]:
        return dict(
            w_p=0,
            w_n=0,
            ridx_p=-1,
            ridx_n=0,
            sig_locs=None,
            sep_vert_in=False,
            sep_vert_out=False,
            vertical_in=False,
            length=1,
            export_nodes=False,
        )

    def draw_layout(self) -> None:
        pinfo = MOSBasePlaceInfo.make_place_info(self.grid, self.params['pinfo'])
        self.draw_base(pinfo)

        w_p: int = self.params['w_p']
        w_n: int = self.params['w_n']
        ridx_p: int = self.params['ridx_p']
        ridx_n: int = self.params['ridx_n']
        # sig_locs: Optional[Mapping[str, float]] = self.params['sig_locs']
        vertical_in: bool = self.params['vertical_in']
        sep_vert_in: bool = self.params['sep_vert_in']
        sep_vert_in = sep_vert_in and vertical_in
        seg_kp: int = self.params['seg_kp']
        seg_drv: int = self.params['seg_drv']
        length: int = self.params['length']
        export_nodes: bool = self.params['export_nodes']

        # --- make masters --- #
        # Inverter params
        inv_diff_params = dict(pinfo=pinfo,
                               seg_kp=seg_kp,
                               seg_drv=seg_drv,
                               w_p=w_p,
                               w_n=w_n,
                               ridx_p=ridx_p,
                               ridx_n=ridx_n,
                               vertical_in=False,
                               sep_vert_in=False,
                               sep_vert_out=False,
                               )
        inv_diff_master = self.new_template(InvDiffCore, params=inv_diff_params)

        # --- Placement --- #
        blk_sp = self.min_sep_col
        cur_col = blk_sp if sep_vert_in else 0
        drv_size = inv_diff_master.num_cols
        # Place inverters
        drivers = []
        for _ in range(length):
            drivers.append(self.add_tile(inv_diff_master,0, cur_col))
            cur_col += drv_size + blk_sp
        self.set_mos_size(cur_col)

        # --- Routing --- #
        # supplies
        vss_list, vdd_list = [], []
        for inst in drivers:
            vss_list.extend(inst.get_all_port_pins('VSS'))
            vdd_list.extend(inst.get_all_port_pins('VDD'))
        self.add_pin('VDD', self.connect_wires(vdd_list)[0])
        self.add_pin('VSS', self.connect_wires(vss_list)[0])

        # connect chain
        for idx in range(1, length):
            in_pin = drivers[idx].get_pin('in')
            inb_pin = drivers[idx].get_pin('inb')
            out_pin = drivers[idx-1].get_pin('out')
            outb_pin = drivers[idx-1].get_pin('outb')
            node = self.connect_wires([in_pin, out_pin])
            node_b = self.connect_wires([inb_pin, outb_pin])
            if export_nodes:
                self.add_pin(f'mid<{idx-1}>', node)
                self.add_pin(f'midb<{idx-1}>', node_b)

        # add input and output pins
        self.add_pin('in', drivers[0].get_pin('in'))
        self.add_pin('inb', drivers[0].get_pin('inb'))
        self.add_pin('out', drivers[-1].get_pin('out'))
        self.add_pin('outb', drivers[-1].get_pin('outb'))

        # get schematic parameters
        self.sch_params = dict(
            inv_diff=inv_diff_master.sch_params,
            length=length,
            export_nodes=export_nodes,
        )
