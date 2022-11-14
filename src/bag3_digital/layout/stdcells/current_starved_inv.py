from typing import Any, Dict, Sequence, Optional, Union, Tuple, Mapping, Type, List

from itertools import chain
from bag.typing import CoordType, TrackType

from pybag.enum import MinLenMode, RoundMode

from bag.util.math import HalfInt
from bag.util.immutable import Param
from bag.design.module import Module
from bag.layout.template import TemplateDB, PyLayInstance
from bag.layout.routing.base import TrackID, WireArray, TrackManager

from xbase.layout.enum import MOSWireType
from xbase.layout.mos.base import MOSBasePlaceInfo, MOSBase
from xbase.layout.mos.data import MOSPorts

# from ...schematic.inv import bag3_digital__current_starved_inv

class CurrentStarvedInvCore(MOSBase):
    """A current-starved inverter.
    """

    def __init__(self, temp_db: TemplateDB, params: Param, **kwargs: Any) -> None:
        MOSBase.__init__(self, temp_db, params, **kwargs)

    # @classmethod
    # def get_schematic_class(cls) -> Optional[Type[Module]]:
    #     return bag3_digital__current_starved_inv

    @classmethod
    def get_params_info(cls) -> Dict[str, str]:
        return dict(
            pinfo='The MOSBasePlaceInfo object.',
            seg_inv='segments of transistors for inverter devices',
            seg_mir='segments of transistors for mirror device',
            seg_p='segments of inverter pmos',
            seg_n='segments of inverter nmos',
            stack_p='number of transistors in a stack.',
            stack_n='number of transistors in a stack.',
            w_p='pmos width, can be list or integer if all widths are the same.',
            w_n='pmos width, can be list or integer if all widths are the same.',
            ridx_p='pmos row index.',
            ridx_n_inv='nmos row index (inverter).',
            ridx_n_mir='nmos row index (mirror).',
            is_guarded='True if it there should be guard ring around the cell',
            sig_locs='Optional dictionary of user defined signal locations',
            vertical_out='True to draw output on vertical metal layer.',
            vertical_sup='True to have supply unconnected on conn_layer.',
            vertical_in='False to not draw the vertical input wire when is_guarded = True.',
            ptap_tile_idx='Ptap tile index.',
            ntap_tile_idx='Ntap tile index.',
            inv_tile_idx='Inverter tile index.',
        )

    @classmethod
    def get_default_param_values(cls) -> Dict[str, Any]:
        return dict(
            seg_inv=-1,
            seg_mir=1,
            seg_p=-1,
            seg_n=-1,
            stack_p=1,
            stack_n=1,
            w_p=0,
            w_n=0,
            ridx_p=-1,
            ridx_n_inv=1,
            ridx_n_mir=0,
            is_guarded=False,
            sig_locs={},
            vertical_out=True,
            vertical_sup=True,
            vertical_in=True,
            ptap_tile_idx=2,
            ntap_tile_idx=0,
            inv_tile_idx=0,
        )

    def draw_layout(self) -> None:
        pinfo = MOSBasePlaceInfo.make_place_info(self.grid, self.params['pinfo'])
        self.draw_base(pinfo)

        grid = self.grid

        seg_inv: int = self.params['seg_inv']
        seg_mir: int = self.params['seg_mir']
        seg_p: int = self.params['seg_p']
        seg_n: int = self.params['seg_n']
        w_p: int = self.params['w_p']
        w_n: int = self.params['w_n']
        stack_p: int = self.params['stack_p']
        stack_n: int = self.params['stack_n']
        ridx_p: int = self.params['ridx_p']
        ridx_n_inv: int = self.params['ridx_n_inv']
        ridx_n_mir: int = self.params['ridx_n_mir']
        is_guarded: bool = self.params['is_guarded']
        sig_locs: Mapping[str, Union[float, HalfInt]] = self.params['sig_locs']
        vertical_out: bool = self.params['vertical_out']
        vertical_sup: bool = self.params['vertical_sup']
        vertical_in: bool = self.params['vertical_in']
        ptap_tile_idx: int = self.params['ptap_tile_idx']
        ntap_tile_idx: int = self.params['ntap_tile_idx']
        inv_tile_idx: int = self.params['inv_tile_idx']

        if seg_p <= 0:
            seg_p = seg_inv
        if seg_n <= 0:
            seg_n = seg_inv
        if seg_p <= 0 or seg_n <= 0:
            raise ValueError('Invalid segments.')

        hm_layer = self.conn_layer + 1
        vm_layer = hm_layer + 1
        if self.top_layer < vm_layer:
            raise ValueError(f'MOSBasePlaceInfo top layer must be at least {vm_layer}')

        # set is_guarded = True if both rows has same orientation
        rpinfo_n = self.get_row_info(ridx_n_inv, tile_idx=inv_tile_idx)
        rpinfo_p = self.get_row_info(ridx_p, tile_idx=inv_tile_idx)
        is_guarded = is_guarded or rpinfo_n.flip == rpinfo_p.flip

        # Placement
        nports_mir = self.add_mos(ridx_n_mir, 0, seg_mir, w=w_n, tile_idx=inv_tile_idx)
        nports_inv = self.add_mos(ridx_n_inv, 0, seg_n, w=w_n, stack=stack_n, tile_idx=inv_tile_idx)
        pports = self.add_mos(ridx_p, 0, seg_p, w=w_p, stack=stack_p, tile_idx=inv_tile_idx)

        self.set_mos_size()

        # get wire_indices from sig_locs
        tr_manager = self.tr_manager
        tr_w_h = tr_manager.get_width(hm_layer, 'sig')
        tr_w_v = tr_manager.get_width(vm_layer, 'sig')
        nout_tidx = sig_locs.get('nout', self.get_track_index(ridx_n_inv, MOSWireType.DS_GATE,
                                                              wire_name='sig', wire_idx=1, tile_idx=inv_tile_idx))
        pout_tidx = sig_locs.get('pout', self.get_track_index(ridx_p, MOSWireType.DS_GATE,
                                                              wire_name='sig', wire_idx=-1, tile_idx=inv_tile_idx))
        nout_tid = TrackID(hm_layer, nout_tidx, tr_w_h)
        pout_tid = TrackID(hm_layer, pout_tidx, tr_w_h)

        pout = self.connect_to_tracks(pports.d, pout_tid, min_len_mode=MinLenMode.NONE)
        nout = self.connect_to_tracks(nports_inv.d, nout_tid, min_len_mode=MinLenMode.NONE)

        if vertical_out:
            vm_tidx = sig_locs.get('out', grid.coord_to_track(vm_layer, pout.middle,
                                                              mode=RoundMode.NEAREST))
            vm_tid = TrackID(vm_layer, vm_tidx, width=tr_w_v)
            self.add_pin('out', self.connect_to_tracks([pout, nout], vm_tid))
        else:
            self.add_pin('out', [pout, nout], connect=True)
            vm_tidx = None

        if is_guarded:
            nin_tidx = sig_locs.get('nin', self.get_track_index(ridx_n_inv, MOSWireType.G,
                                                                wire_name='sig', wire_idx=0, tile_idx=inv_tile_idx))
            pin_tidx = sig_locs.get('pin', self.get_track_index(ridx_p, MOSWireType.G,
                                                                wire_name='sig', wire_idx=-1, tile_idx=inv_tile_idx))

            nin = self.connect_to_tracks(nports_inv.g, TrackID(hm_layer, nin_tidx, width=tr_w_h))
            pin = self.connect_to_tracks(pports.g, TrackID(hm_layer, pin_tidx, width=tr_w_h))
            self.add_pin('pin', pin, hide=True)
            self.add_pin('nin', nin, hide=True)
            if vertical_in:
                in_tidx = self.grid.find_next_track(vm_layer, nin.lower,
                                                    tr_width=tr_w_v, mode=RoundMode.GREATER_EQ)
                if vm_tidx is not None:
                    in_tidx = min(in_tidx,
                                  self.tr_manager.get_next_track(vm_layer, vm_tidx, 'sig', 'sig',
                                                                 up=False))

                in_tidx = sig_locs.get('in', in_tidx)
                self.add_pin('in', self.connect_to_tracks([pin, nin],
                                                          TrackID(vm_layer, in_tidx, width=tr_w_v)))
            else:
                self.add_pin('in', [pin, nin], connect=True)
        else:
            in_tidx = sig_locs.get('in', None)
            if in_tidx is None:
                in_tidx = sig_locs.get('nin', None)
                if in_tidx is None:
                    default_tidx = self.get_track_index(ridx_n_inv, MOSWireType.G,
                                                        wire_name='sig', wire_idx=0, tile_idx=inv_tile_idx)
                    in_tidx = sig_locs.get('pin', default_tidx)

            in_warr = self.connect_to_tracks([nports_inv.g, pports.g],
                                             TrackID(hm_layer, in_tidx, width=tr_w_h))
            self.add_pin('in', in_warr)
            self.add_pin('pin', in_warr, hide=True)
            self.add_pin('nin', in_warr, hide=True)

        self.add_pin(f'pout', pout, hide=True)
        self.add_pin(f'nout', nout, hide=True)

        ref_v_tid = self.get_track_id(ridx_n_mir, MOSWireType.G, wire_name='sig', wire_idx=0, tile_idx=inv_tile_idx)
        ref_v = self.connect_to_tracks(nports_mir.g, ref_v_tid)
        self.add_pin('ref_v', ref_v, show=True)

        ns_tid = self.get_track_id(ridx_n_inv, MOSWireType.DS_GATE, wire_name='sig', wire_idx=0, tile_idx=inv_tile_idx)
        ns_tie = self.connect_to_tracks(nports_inv.s, ns_tid)

        if vm_tidx:
            ns_tidx = tr_manager.get_next_track(vm_layer, vm_tidx, 'sig', 'sig', up=False)
            ns_tid = TrackID(vm_layer, ns_tidx, width=tr_w_v)
        else:
            ns_tid = self.track_to_track(vm_layer, nports_mir.d[0])

        ns = self.connect_to_tracks(ns_tie, ns_tid)

        ns_mir_tidx = self.get_track_index(ridx_n_mir, MOSWireType.DS_GATE, wire_name='sig',
                                          wire_idx=0, tile_idx=inv_tile_idx)
        self.connect_through(ns, nports_mir.d, tr_manager, connect_tidx=ns_mir_tidx)

        xr = self.bound_box.xh

        if vertical_sup:
            self.add_pin('VDD', pports.s, connect=True)
            self.add_pin('VSS', nports_mir.s, connect=True)
        else:
            raise NotImplementedError('Current-starved inverters currently do not support horizontal supply rails.')

        inv_tile_pinfo, _, _ = self.get_tile_info(inv_tile_idx)
        default_wp = inv_tile_pinfo.get_row_place_info(ridx_p).row_info.width
        default_wn = inv_tile_pinfo.get_row_place_info(ridx_n_inv).row_info.width
        thp = inv_tile_pinfo.get_row_place_info(ridx_p).row_info.threshold
        thn = inv_tile_pinfo.get_row_place_info(ridx_n_inv).row_info.threshold
        lch = inv_tile_pinfo.lch
        self.sch_params = dict(
            seg_p=seg_p,
            seg_n=seg_n,
            lch=lch,
            w_p=default_wp if w_p == 0 else w_p,
            w_n=default_wn if w_n == 0 else w_n,
            th_n=thn,
            th_p=thp,
            stack_p=stack_p,
            stack_n=stack_n,
        )

    def track_to_track(self, targ_layer: int, ref_tid: TrackID,
                       mode: RoundMode = RoundMode.NEAREST) -> TrackID:
        ref_layer = ref_tid.layer_id
        coord = self.grid.track_to_coord(ref_layer, ref_tid.base_index)
        return self.grid.coord_to_track(targ_layer, coord, mode=mode)

    def connect_through(self, first_warr: WireArray, second_warr: WireArray,
                        tr_manager: TrackManager,
                        connect_pt: CoordType = None, connect_tidx: TrackType = None,
                        mode: MinLenMode = MinLenMode.MIDDLE) -> WireArray:

        first_layer = first_warr.layer_id
        second_layer = second_warr.layer_id
        start_warr = first_warr if first_layer < second_layer else second_warr
        end_warr = second_warr if first_layer < second_layer else first_warr

        if first_layer == second_layer:
            print("Connecting wires on the same layer should be done with self.connect_wires")
            return self.connect_wires([first_warr, second_warr])

        first_coord = self.grid.track_to_coord(first_layer, first_warr.track_id.base_index)
        if connect_pt is not None:
            second_coord = connect_pt
        elif connect_tidx is not None:
            second_coord = self.grid.track_to_coord(second_layer, connect_tidx)
        else:
            raise ValueError('Must specify either connect_pt or connect_tidx')

        last_warr = start_warr
        last_coord = second_coord
        for next_layer in range(start_warr.layer_id + 1, end_warr.layer_id):
            next_tid = TrackID(next_layer, self.grid.coord_to_track(next_layer, last_coord, mode=mode),
                               width=tr_manager.get_width(next_layer, 'sig'))
            next_wire = self.connect_to_tracks(last_warr, next_tid)
            last_warr = next_wire
            last_coord = self.grid.track_to_coord(next_layer, next_tid.base_index)
        return self.connect_to_track_wires(next_wire, end_warr)