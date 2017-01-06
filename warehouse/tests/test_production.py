# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


class TestProduction(TransactionCase):
    ''' 测试组装单和拆卸单 '''
    def setUp(self):
        super(TestProduction, self).setUp()

        self.env.ref('core.goods_category_1').account_id = self.env.ref('finance.account_goods').id
        self.env.ref('warehouse.wh_in_whin0').date = '2016-02-06'

        self.assembly = self.browse_ref('warehouse.wh_assembly_ass0')
        self.assembly_mutli = self.browse_ref('warehouse.wh_assembly_ass1')

        self.assembly_mutli_keyboard_mouse_1 = self.browse_ref('warehouse.wh_move_line_ass2')
        self.assembly_mutli_keyboard_mouse_2 = self.browse_ref('warehouse.wh_move_line_ass3')

        self.disassembly = self.browse_ref('warehouse.wh_disassembly_dis1')
        self.disassembly_bom = self.browse_ref('warehouse.wh_bom_0')

        self.disassembly_mouse = self.browse_ref('warehouse.wh_move_line_8')
        self.disassembly_keyboard = self.browse_ref('warehouse.wh_move_line_9')

        self.overage_in = self.browse_ref('warehouse.wh_in_whin0')
        self.overage_in.approve_order()

        self.outsource_out1 = self.browse_ref('warehouse.outsource_out1')

    def test_approve(self):
        # 库存不足的时候直接拆卸，会报没有库存的异常
        with self.assertRaises(UserError):
            self.disassembly.approve_order()

        # 先组装，后拆卸可以正常出入库
        self.assembly.approve_order()
        self.disassembly.approve_order()

        self.assertEqual(self.assembly.state, 'done')
        self.assertEqual(self.disassembly.state, 'done')

    def test_cancel(self):
        self.assembly.approve_order()
        self.disassembly.approve_order()

        # 组装的产品已经被拆卸过了，此时会报异常
        with self.assertRaises(UserError):
            self.assembly.cancel_approved_order()

        self.disassembly.cancel_approved_order()
        self.assembly.cancel_approved_order()

        # 取消后的单据的状态为draft
        self.assertEqual(self.assembly.state, 'draft')
        self.assertEqual(self.disassembly.state, 'draft')

    def test_unlink(self):
        self.assembly.approve_order()
        self.disassembly.approve_order()

        # 没法删除已经审核果的单据
        with self.assertRaises(UserError):
            self.assembly.unlink()

        # 组装的产品已经被拆卸过了，此时会报异常
        with self.assertRaises(UserError):
            self.assembly.unlink()

        self.disassembly.cancel_approved_order()
        self.assembly.cancel_approved_order()

        # 反审核后可以被删除掉
        self.assembly.unlink()
        self.disassembly.unlink()

        # 删除后的单据应该不存在
        self.assertTrue(not self.disassembly.exists())
        self.assertTrue(not self.assembly.exists())

    def test_create(self):
        temp_assembly = self.env['wh.assembly'].create({'name': '/'})
        temp_disassembly = self.env['wh.disassembly'].create({'name': '/'})

        # 编号应该由ir.sequence指定，不应该等于指定值
        self.assertNotEqual(temp_assembly.name, '/')
        self.assertNotEqual(temp_disassembly.name, '/')

        # 验证origin是否正确
        self.assertEqual(temp_assembly.origin, 'wh.assembly')
        self.assertEqual(temp_disassembly.origin, 'wh.disassembly')

    def test_apportion(self):
        self.assembly_mutli.fee = 0
        self.assembly_mutli.approve_order()

        # demo数据中成本为鼠标 40 * 2，键盘 80 * 2，所以成本应该为平摊为120
        self.assertEqual(self.assembly_mutli_keyboard_mouse_1.cost_unit, 120)
        self.assertEqual(self.assembly_mutli_keyboard_mouse_2.cost_unit, 120)

        self.assembly_mutli.cancel_approved_order()
        self.assembly_mutli.fee = 100
        self.assembly_mutli.approve_order()

        # 此时组装费用为100，成本增加了100，所以平摊成本增加50
        self.assertEqual(self.assembly_mutli_keyboard_mouse_1.cost_unit, 170)
        self.assertEqual(self.assembly_mutli_keyboard_mouse_2.cost_unit, 170)

        # 取消掉当前的单据，防止其他单据的库存不足
        self.assembly_mutli.cancel_approved_order()

        self.assembly.fee = 0
        self.assembly.approve_order()

        # demo数据中入库的成本为鼠标 40 * 1，键盘 80 * 2, 所以成本应该为100
        self.assertEqual(self.assembly.line_in_ids.cost_unit, 100)

        self.assembly.cancel_approved_order()
        self.assembly.fee = 100
        self.assembly.approve_order()

        # 指定组装费用位100，此时成本应该位150
        self.assertEqual(self.assembly.line_in_ids.cost_unit, 150)

        self.disassembly.approve_order()

        # 150的成本被拆分成鼠标 * 1(成本40) + 键盘 * 1（成本80）,所以此时应该均分为50 + 100
        self.assertEqual(self.disassembly_mouse.cost_unit, 50)
        self.assertEqual(self.disassembly_keyboard.cost_unit, 100)

        self.disassembly.cancel_approved_order()
        self.disassembly.fee = 120

        self.disassembly.approve_order()
        # 指定拆卸费用位120，此时平分270，此时应该位 90 + 180
        self.assertEqual(self.disassembly_mouse.cost_unit, 90)
        self.assertEqual(self.disassembly_keyboard.cost_unit, 180)

    def test_wizard_bom(self):
        self.assembly.bom_id = False
        action = self.assembly.update_bom()

        temp_action = {
            'type': 'ir.actions.act_window',
            'res_model': 'save.bom.memory',
            'view_mode': 'form',
            'target': 'new',
        }

        # 当bom_id不存在的时候，此时保存bom，会自动返回一个wizard
        self.assertEqual(action, temp_action)
        save_bom_memory = self.env['save.bom.memory'].with_context({
            'active_model': self.assembly._name,
            'active_ids': self.assembly.id
        }).create({'name': 'temp'})

        save_bom_memory.save_bom()
        self._test_assembly_bom(self.assembly, self.assembly.bom_id)

        self.disassembly.bom_id = False
        action = self.disassembly.update_bom()

        # 当bom_id不存在的时候，此时保存bom，会自动返回一个wizard
        self.assertEqual(action, temp_action)
        save_bom_memory = self.env['save.bom.memory'].with_context({
            'active_model': self.disassembly._name,
            'active_ids': self.disassembly.id
        }).create({'name': 'temp'})

        save_bom_memory.save_bom()

        self._test_disassembly_bom(self.disassembly, self.disassembly.bom_id)

    def test_bom(self):
        # 创建一个新的临时bom
        self.assembly.bom_id = self.env['wh.bom'].create({'name': 'temp', 'type': 'assembly'})

        # 将当前的组装单保存的临时bom上去
        self.assembly.update_bom()
        # 测试bom和组装单是否一致
        self._test_assembly_bom(self.assembly, self.assembly.bom_id)

        # 删除掉明细行，防止onchange之后明细行上存在历史的数据(缓存)
        self.assembly.line_in_ids.unlink()
        # 当有一个明细行没有值的时候，此时无法通过明细行检测
        with self.assertRaises(UserError):
            self.assembly.check_parent_length()

        self.assembly.line_out_ids.unlink()

        assembly_values = {
            'bom_id': self.assembly.bom_id,
            'line_in_ids': False,
            'line_out_ids': False,
        }
        # 使用onchange来触发bom的改变，由于相关的bug，只能使用这种方案
        # results = self.assembly.onchange(assembly_values, 'bom_id', {'bom_id': 'true'})
        # 测试使用bom后，明细行上和bom的是否一致
        # self._test_assembly_bom_by_results(self.assembly, self.assembly.bom_id, results['value'])

        self.disassembly.update_bom()
        self._test_disassembly_bom(self.disassembly, self.disassembly.bom_id)

        self.disassembly.line_in_ids.unlink()
        # 当有一个明细行没有值的时候，此时无法通过明细行检测
        with self.assertRaises(UserError):
            self.disassembly.check_parent_length()

        self.disassembly.line_out_ids.unlink()

        disassembly_values = {
            'bom_id': self.disassembly.bom_id,
            'line_in_ids': False,
            'line_out_ids': False,
        }
        # results = self.disassembly.onchange(disassembly_values, 'bom_id', {'bom_id': 'true'})
        # self._test_disassembly_bom_by_results(self.disassembly, self.disassembly.bom_id, results['value'])

    def _test_assembly_bom_by_results(self, assembly, bom, results):
        self._test_bom(assembly, bom, parent_results=results['line_in_ids'], child_results=results['line_out_ids'])

    def _test_disassembly_bom_by_results(self, disassembly, bom, results):
        self._test_bom(disassembly, bom, parent_results=results['line_out_ids'], child_results=results['line_in_ids'])

    def _test_assembly_bom(self, assembly, bom):
        self._test_bom(assembly, bom, parent_attr='line_in_ids', child_attr='line_out_ids')

    def _test_disassembly_bom(self, disassembly, bom):
        self._test_bom(disassembly, bom, parent_attr='line_out_ids', child_attr='line_in_ids')

    def _test_bom(self, assembly, bom, parent_attr='line_in_ids', child_attr='line_out_ids',
                  parent_results=None, child_results=None):
        bom_parent_ids = [(parent.goods_id.id, parent.goods_qty) for parent in bom.line_parent_ids]
        bom_child_ids = [(child.goods_id.id, child.goods_qty) for child in bom.line_child_ids]

        if parent_results and child_results:
            assembly_parent_ids = [(parent[2]['goods_id'], parent[2]['goods_qty']) for parent in parent_results]
            assembly_child_ids = [(child[2]['goods_id'], child[2]['goods_qty']) for child in child_results]
        else:
            assembly_parent_ids = [(parent.goods_id.id, parent.goods_qty) for parent in getattr(assembly, parent_attr)]
            assembly_child_ids = [(child.goods_id.id, child.goods_qty) for child in getattr(assembly, child_attr)]

        self.assertEqual(len(bom_parent_ids), len(assembly_parent_ids))
        self.assertEqual(len(bom_child_ids), len(assembly_child_ids))

        for parent in assembly_parent_ids:
            self.assertTrue(parent in bom_parent_ids)

        for child in assembly_child_ids:
            self.assertTrue(child in bom_child_ids)

    def test_onchange_goods_id(self):
        ''' 测试 onchange_goods_id '''
        # 组装单 onchange_goods_id
        wh_assembly_ass2 = self.browse_ref('warehouse.wh_assembly_ass2')
        wh_assembly_ass2.goods_id =  self.env.ref('goods.keyboard_mouse').id
        wh_assembly_ass2.onchange_goods_id()

        # 委外加工单 onchange_goods_id
        self.outsource_out1.goods_id =  self.env.ref('goods.keyboard_mouse')
        self.outsource_out1.onchange_goods_id()

        # 拆卸单 onchange_goods_id
        wh_disassembly_dis3 = self.browse_ref('warehouse.wh_disassembly_dis3')
        wh_disassembly_dis3.goods_id =  self.env.ref('goods.keyboard_mouse').id
        wh_disassembly_dis3.onchange_goods_id()

    def test_assembly_onchange_goods_qty(self):
        ''' 测试 组装单 onchange_goods_qty '''
        # no bom_id
        wh_assembly_ass2 = self.browse_ref('warehouse.wh_assembly_ass2')
        wh_assembly_ass2.goods_qty = 2
        wh_assembly_ass2.onchange_goods_qty()
        
        # self.line_in_ids
        wh_assembly_ass0 = self.browse_ref('warehouse.wh_assembly_ass0')
        wh_assembly_ass0.goods_qty = 2
        wh_assembly_ass0.onchange_goods_qty()

        # has bom_id
        wh_assembly_ass2.type = 'assembly'
        wh_assembly_ass2.name = 'combination'
        wh_assembly_ass2.bom_id = self.env.ref('warehouse.wh_bom_0').id
        wh_assembly_ass2.goods_qty = 1
        wh_assembly_ass2.onchange_goods_qty()

    def test_outsource_onchange_goods_qty_no_bom(self):
        ''' 测试 委外加工单 onchange_goods_qty 不存在 物料清单 '''
        # no bom_id
        self.outsource_out1.bom_id = False
        self.outsource_out1.goods_qty = 2
        self.outsource_out1.onchange_goods_qty()

    def test_outsource_onchange_goods_qty_has_bom(self):
        ''' 测试 委外加工单 onchange_goods_qty 存在 物料清单 '''
        # has bom_id
        wh_bom_0 = self.env.ref('warehouse.wh_bom_0')
        wh_bom_0.type = 'outsource'
        wh_bom_0.name = 'out source'
        self.outsource_out1.bom_id = self.env.ref('warehouse.wh_bom_0').id
        self.outsource_out1.goods_qty = 1
        self.outsource_out1.onchange_goods_qty()

    def test_outsource_onchange_bom_no_bom(self):
        ''' 测试  委外加工单 onchange_bom 不存在 物料清单 '''
        # no bom_id
        self.outsource_out1.bom_id = False
        self.outsource_out1.onchange_bom()
        self.assertEqual(self.outsource_out1.goods_qty, 1.0)

    def test_outsource_onchange_bom_has_bom(self):
        ''' 测试  委外加工单 onchange_bom 存在 物料清单 '''
        wh_bom = self.env.ref('warehouse.wh_bom_0')
        # has bom_id
        self.outsource_out1.bom_id = wh_bom.id
        self.outsource_out1.onchange_bom()

    def test_outsource_onchange_bom_has_bom_inLine(self):
        ''' 测试  委外加工单 onchange_bom 存在 物料清单 line_in_ids > 1'''
        # has bom_id, line_in_ids > 1
        wh_bom = self.env.ref('warehouse.wh_bom_0')
        wh_bom.line_parent_ids.create({
                                       'bom_id': self.env.ref('warehouse.wh_bom_0').id,
                                       'type': 'parent',
                                       'goods_id': self.env.ref('goods.cable').id,
                                       'goods_qty': 1
                                       })
        self.outsource_out1.bom_id = wh_bom.id
        self.outsource_out1.onchange_bom()
        self.assertTrue(self.outsource_out1.is_many_to_many_combinations)

    def test_outsource_approve_feeding(self):
        ''' 测试  委外加工单 审核: 存在委外费用生成结算单 '''
        self.outsource_out1.outsource_partner_id = self.env.ref('core.lenovo').id
        self.outsource_out1.approve_feeding()

    def test_outsource_approve_feeding_no_in_line(self):
        ''' 测试  委外加工单 投料：一个明细行没有值 '''
        # 当一个明细行没有值时，raise 委外加工单必须存在组合件和子件明细行
        self.outsource_out1.line_in_ids.unlink()
        with self.assertRaises(UserError):
            self.outsource_out1.approve_feeding()

    def test_outsource_approve_order_has_fee(self):
        ''' 测试  委外加工单 审核: 存在委外费用生成结算单 '''
        self.outsource_out1.outsource_partner_id = self.env.ref('core.lenovo').id
        self.outsource_out1.outsource_fee = 100
        self.outsource_out1.approve_order()

    def test_outsource_cancel_approved_order(self):
        ''' 测试  委外加工单 反审核 '''
        self.outsource_out1.outsource_partner_id = self.env.ref('core.lenovo').id
        self.outsource_out1.outsource_fee = 100
        self.outsource_out1.approve_order()
        self.outsource_out1.cancel_approved_order()

    def test_outsource_unlink(self):
        ''' 测试  委外加工单 删除 '''
        self.outsource_out1.unlink()

    def test_outsource_create(self):
        ''' 测试  委外加工单 创建 '''
        self.outsource_out1.create({
                                    'outsource_partner_id': self.env.ref('core.lenovo').id,
                                    'outsource_fee': 10,
                                    })

    def test_disassembly_onchange_goods_qty(self):
        ''' 测试 拆卸单 onchange_goods_qty '''
        # has bom_id
        wh_disassembly_dis3 = self.browse_ref('warehouse.wh_disassembly_dis3')
        wh_disassembly_dis3.goods_qty = 2
        wh_disassembly_dis3.onchange_goods_qty()

    def test_disassembly_onchange_goods_qty_no_bom(self):
        ''' 测试 拆卸单 onchange_goods_qty 没有物料清单 '''
        # self.line_out_ids
        wh_disassembly_dis3 = self.browse_ref('warehouse.wh_disassembly_dis3')
        wh_disassembly_dis3.bom_id = False
        wh_disassembly_dis3.goods_id = self.env.ref('goods.keyboard_mouse').id
        wh_disassembly_dis3.onchange_goods_id()
        wh_disassembly_dis3.goods_qty = 2
        wh_disassembly_dis3.onchange_goods_qty()

    def test_assembly_onchange_bom(self):
        ''' 测试  组装单 onchange_bom '''
        # no bom_id
        wh_assembly_ass0 = self.browse_ref('warehouse.wh_assembly_ass0')
        wh_assembly_ass0.onchange_bom()
        self.assertEqual(wh_assembly_ass0.goods_qty, 1.0)

    def test_assembly_has_bom_id(self):
        '''  测试 组装单 onchange_bom '''
        # has bom_id
        wh_assembly_ass0 = self.env.ref('warehouse.wh_assembly_ass0')
        wh_assembly_ass0.bom_id = self.env.ref('warehouse.wh_bom_0').id
        wh_assembly_ass0.onchange_bom()

    def test_assembly_has_bom_line_in(self):
        ''' 测试 组装单 bom_id 的组合件 大于 1 '''
        # bom_id 的组合件 大于 1行时，len(line_in_ids)>1
        wh_assembly_ass0 = self.env.ref('warehouse.wh_assembly_ass0')
        wh_bom = self.env.ref('warehouse.wh_bom_0')
        wh_bom.type = 'assembly'
        wh_bom.line_parent_ids.create({
                                       'bom_id': self.env.ref('warehouse.wh_bom_0').id,
                                       'type': 'parent',
                                       'goods_id': self.env.ref('goods.cable').id,
                                       'goods_qty': 1
                                       })

        wh_assembly_ass0.bom_id = wh_bom.id
        wh_assembly_ass0.onchange_bom()
        self.assertTrue(wh_assembly_ass0.is_many_to_many_combinations)

    def test_disassembly_onchange_bom(self):
        ''' 测试 拆卸单 onchange_bom '''
        # no bom_id
        wh_disassembly_dis3 = self.env.ref('warehouse.wh_disassembly_dis3')

        wh_disassembly_dis3.bom_id = False
        wh_disassembly_dis3.onchange_bom()
        self.assertEqual(wh_disassembly_dis3.goods_qty, 1.0)

    def test_disassembly_has_bom(self):
        ''' 测试拆卸单 存在 bom '''
        # has bom_id
        wh_disassembly_dis3 = self.env.ref('warehouse.wh_disassembly_dis3')
        bom_copy_1 = self.env.ref('warehouse.wh_bom_0').copy()
        self.bom_id = bom_copy_1.id
        wh_disassembly_dis3.bom_id = bom_copy_1.id
        wh_disassembly_dis3.onchange_bom()

    def test_disassembly_has_bom_out_line(self):
        ''' 测试拆卸单 bom_id 的组合件 大于 1 '''
        # 拆卸单 bom_id 的组合件 大于 1行时，len(line_out_ids)>1
        wh_disassembly_dis3 = self.env.ref('warehouse.wh_disassembly_dis3')

        wh_bom = self.env.ref('warehouse.wh_bom_0')
        wh_bom.line_parent_ids.create({
                                       'bom_id': self.env.ref('warehouse.wh_bom_0').id,
                                       'type': 'parent',
                                       'goods_id': self.env.ref('goods.cable').id,
                                       'goods_qty': 1
                                       })

        self.bom_id = self.disassembly_bom.id
        wh_disassembly_dis3.bom_id = wh_bom.id
        wh_disassembly_dis3.onchange_bom()
        self.assertTrue(wh_disassembly_dis3.is_many_to_many_combinations)

    def test_cancel_approve_order_has_voucher(self):
        ''' 测试 拆卸单 反审核 删除发票 '''
        self.assembly.approve_order()
        self.disassembly.fee = 10
#         print "cost", self.disassembly.line_out_ids[0].cost
#         print "cost in", self.disassembly.line_in_ids[0].cost, self.disassembly.line_in_ids[1].cost
#         self.disassembly.approve_order()
# 
#         self.disassembly.cancel_approved_order()
