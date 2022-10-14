from typing import Any, Mapping, Optional, Type

from pybag.enum import RoundMode, MinLenMode

from bag.util.immutable import Param
from bag.design.module import Module
from bag.layout.template import TemplateDB
from bag.layout.routing.base import TrackID

from xbase.layout.enum import MOSWireType
from xbase.layout.mos.base import MOSBasePlaceInfo, MOSBase

from .gates import InvCore
from ...schematic.inv_diff import bag3_digital__inv_diff


class InvDiffCore(MOSBase):
    """Differential inverter cell using inverters"""
    def __init__(self, temp_db: TemplateDB, params: Param, **kwargs: Any) -> None:
        MOSBase.__init__(self, temp_db, params, **kwargs)

    @classmethod
    def get_schematic_class(cls) -> Optional[Type[Module]]:
        return bag3_digital__inv_diff

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
            vertical_in='True to have inputs on vertical layer; True by default',
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
        sep_vert_out: bool = self.params['sep_vert_out']
        seg_kp: int = self.params['seg_kp']
        seg_drv: int = self.params['seg_drv']

        # --- make masters --- #
        # get tracks
        pg0_tidx = self.get_track_index(ridx_p, MOSWireType.G, 'sig', 0)
        ng0_tidx = self.get_track_index(ridx_n, MOSWireType.G, 'sig', 1)

        # Keeper inverters
        inv_kp_params = dict(pinfo=pinfo, seg=seg_kp, w_p=w_p, w_n=w_n,
                             ridx_p=ridx_p, ridx_n=ridx_n, vertical_out=False,
                             sig_locs={'nin': pg0_tidx})
        inv_kp_master = self.new_template(InvCore, params=inv_kp_params)
        inv_kp_ncols = inv_kp_master.num_cols

        # Input inverters
        inv_drv_params = dict(pinfo=pinfo, seg=seg_drv, w_p=w_p, w_n=w_n,
                              ridx_p=ridx_p, ridx_n=ridx_n, vertical_out=False,
                              sig_locs={'nin': ng0_tidx})
        inv_drv_master = self.new_template(InvCore, params=inv_drv_params)
        inv_drv_ncols = inv_drv_master.num_cols

        # --- Placement --- #
        blk_sp = self.min_sep_col
        cur_col = blk_sp if sep_vert_in else 0
        inv_in = self.add_tile(inv_drv_master, 0, cur_col)
        inv_inb = self.add_tile(inv_drv_master, 1, cur_col)

        cur_col += inv_drv_ncols + blk_sp + inv_kp_ncols
        inv_fb0 = self.add_tile(inv_kp_master, 0, cur_col, flip_lr=True)
        inv_fb1 = self.add_tile(inv_kp_master, 1, cur_col, flip_lr=True)

        cur_col += (blk_sp * sep_vert_out)
        self.set_mos_size(cur_col)

        # --- Routing --- #
        # supplies
        vss_list, vdd_list = [], []
        for inst in (inv_in, inv_inb, inv_fb0, inv_fb1):
            vss_list.append(inst.get_pin('VSS'))
            vdd_list.append(inst.get_pin('VDD'))
        self.add_pin('VDD', self.connect_wires(vdd_list)[0])
        self.add_pin('VSS', self.connect_wires(vss_list)[0])

        hm_layer = self.conn_layer + 1
        vm_layer = hm_layer + 1

        # input pins on vm_layer
        w_sig_vm = self.tr_manager.get_width(vm_layer, 'sig')
        if vertical_in:
            close_track = self.grid.coord_to_track(inv_in.get_pin('nin').lower,
                                                   vm_layer,
                                                   RoundMode.NEAREST)
            _, vm_locs = self.tr_manager.place_wires(vm_layer, ['sig', 'sig'],
                                                     close_track, -1)
            if sep_vert_in:
                tidx0, tidx1 = vm_locs[0], vm_locs[1]
            else:
                tidx0, tidx1 = vm_locs[1], vm_locs[1]
            in_vm = self.connect_to_tracks(inv_in.get_pin('nin'),
                                           TrackID(vm_layer, tidx0, w_sig_vm),
                                           min_len_mode=MinLenMode.MIDDLE)
            self.add_pin('in', in_vm)
            inb_vm = self.connect_to_tracks(inv_inb.get_pin('nin'),
                                            TrackID(vm_layer, tidx1, w_sig_vm),
                                            min_len_mode=MinLenMode.MIDDLE)
            self.add_pin('inb', inb_vm)
        else:
            self.reexport(inv_in.get_port('nin'), net_name='in', hide=False)
            self.reexport(inv_inb.get_port('nin'), net_name='inb', hide=False)

        # outputs on vm_layer
        _tidx1 = self.grid.coord_to_track(vm_layer,
                                          cur_col * self.sd_pitch,
                                          RoundMode.NEAREST)
        if sep_vert_out:
            raise NotImplementedError('Not implemented yet.')

        # get vm_layer tracks for mid and midb
        mid_coord = inv_in.get_pin('nin').upper
        mid_tidx = self.grid.coord_to_track(vm_layer, mid_coord,
                                            RoundMode.NEAREST)
        mid_tidx = self.tr_manager.get_next_track(vm_layer, mid_tidx,
                                                  'sig', 'sig', 1)
        _, vm_locs = self.tr_manager.place_wires(vm_layer,
                                                 ['sig', 'sig'],
                                                 mid_tidx)
        mid = self.connect_to_tracks([inv_in.get_pin('pout'),
                                      inv_in.get_pin('nout'),
                                     inv_fb0.get_pin('pout'),
                                     inv_fb0.get_pin('nout'),
                                     inv_fb1.get_pin('nin')],
                                     TrackID(vm_layer, vm_locs[1], w_sig_vm))
        midb = self.connect_to_tracks([inv_inb.get_pin('pout'),
                                       inv_inb.get_pin('nout'),
                                      inv_fb1.get_pin('pout'),
                                      inv_fb1.get_pin('nout'),
                                      inv_fb0.get_pin('nin')],
                                      TrackID(vm_layer, vm_locs[-2], w_sig_vm))

        # draw output pins
        out_hm = self.connect_to_tracks(mid,
                                        inv_in.get_pin('nin').track_id,
                                        min_len_mode=MinLenMode.MIDDLE)
        outb_hm = self.connect_to_tracks(midb,
                                         inv_inb.get_pin('nin').track_id,
                                         min_len_mode=MinLenMode.MIDDLE)
        self.add_pin('out', out_hm, label='out')
        self.add_pin('outb', outb_hm, label='outb')

        # get schematic parameters
        self.sch_params = dict(
            inv_in=inv_drv_master.sch_params,
            inv_fb=inv_kp_master.sch_params,
        )
