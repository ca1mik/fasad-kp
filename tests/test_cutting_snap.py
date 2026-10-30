from tests.test_kp_demo import demo_url, page
from tests.test_portable_workflow import sample


def prepare(page, url):
    page.set_viewport_size({'width': 1600, 'height': 1300})
    sample(page, url)
    page.evaluate('''() => {
      const o=data.orders[0];o.parts=[{id:'A',name:'A',height:200,width:100,qty:1,grain:false,thickness:16,color:''},{id:'B',name:'B',height:200,width:100,qty:1,grain:false,thickness:16,color:''}];
      o.materialSpec={...o.materialSpec,sheetWidth:1000,sheetHeight:800,margin:10,kerf:4};o.manualLayout=null;saveData();renderCutting(o.id);
    }''')
    panel=page.locator('#mapLayoutSettings')
    for name,value in {'gapX':65,'gapY':20,'marginLeft':30,'marginRight':40,'marginTop':50,'marginBottom':60}.items():
        panel.locator(f'[data-layout-param={name}]').fill(str(value))
    panel.locator('[data-snap=edges]').uncheck()
    panel.locator('[data-snap=tolerance]').fill('30')
    panel.locator('[data-layout-apply]').click()
    page.evaluate('''() => {
      const o=data.orders[0],base=calculateNesting(o.parts,o.materialSpec,o.materialSpecs);
      o.manualLayout=FasadCuttingLayout.revise(o,base,'B#1',{x:600,y:400});saveData();updateCuttingResults(o);
    }''')


def drag_near_neighbour(page, editor=False, shift=False):
    root=page.locator('.layout-editor') if editor else page.locator('#cuttingMaps')
    a=root.locator('[data-layout-key="A#1"] rect.piece')
    b=root.locator('[data-layout-key="B#1"] rect.piece')
    b.scroll_into_view_if_needed()
    ax=float(a.get_attribute('x'));ay=float(a.get_attribute('y'));aw=float(a.get_attribute('width'))
    bw=float(b.get_attribute('width'));bh=float(b.get_attribute('height'))
    svg=root.locator('svg').first.bounding_box();box=b.bounding_box()
    x,y=ax+aw+65+9,ay
    page.mouse.move(box['x']+box['width']/2,box['y']+box['height']/2)
    if shift:page.keyboard.down('Shift')
    page.mouse.down()
    page.mouse.move(svg['x']+(x+bw/2)*svg['width']/1000,svg['y']+(y+bh/2)*svg['height']/800,steps=10)
    page.mouse.up()
    if shift:page.keyboard.up('Shift')
    return ax+aw+65


def test_main_map_snaps_to_part_with_one_gap_and_shift_bypasses(demo_url,page):
    page,errors=page
    prepare(page,demo_url)
    expected=drag_near_neighbour(page)
    piece=page.locator('#cuttingMaps [data-layout-key="B#1"]')
    assert float(piece.get_attribute('data-x')) == expected
    expected=drag_near_neighbour(page,shift=True)
    assert abs(float(piece.get_attribute('data-x'))-(expected+9)) <= 1
    # Saving magnet preferences must not discard the existing manual positions.
    saved=page.evaluate('JSON.stringify(data.orders[0].manualLayout)')
    panel=page.locator('#mapLayoutSettings')
    panel.locator('[data-snap=tolerance]').fill('50')
    panel.locator('[data-layout-apply]').click()
    assert page.evaluate('JSON.stringify(data.orders[0].manualLayout)') == saved
    page.reload()
    assert page.locator('#mapLayoutSettings [data-layout-param=gapX]').input_value() == '65'
    assert page.locator('#mapLayoutSettings [data-layout-param=gapY]').input_value() == '20'
    assert page.locator('#mapLayoutSettings [data-layout-param=marginRight]').input_value() == '40'
    assert page.locator('#mapLayoutSettings [data-snap=tolerance]').input_value() == '50'


def test_full_editor_uses_same_magnet_and_settings_undo(demo_url,page):
    page,errors=page
    prepare(page,demo_url)
    page.locator('#openManualEditor').click()
    expected=drag_near_neighbour(page,editor=True)
    editor=page.locator('.layout-editor')
    assert float(editor.locator('[data-layout-key="B#1"]').get_attribute('data-x')) == expected
    assert 'Магнит:' in editor.locator('.editor-status').inner_text() or 'Позиция допустима' in editor.locator('.editor-status').inner_text()
    page.on('dialog',lambda dialog: dialog.accept())
    editor.locator('.layout-settings summary').click()
    editor.locator('[data-layout-param=gapY]').fill('35')
    editor.locator('[data-layout-apply]').click()
    assert '35 мм (X/Y)' in editor.locator('.editor-sheet').first.inner_text()
    assert page.evaluate('data.orders[0].materialSpec.gapY') == 20
    editor.locator('[data-edit=undo]').click()
    assert editor.locator('[data-layout-param=gapY]').input_value() == '20'
    editor.locator('[data-edit=save]').click()
    page.reload()
    assert float(page.locator('#cuttingMaps [data-layout-key="B#1"]').get_attribute('data-x')) == expected


def test_preferences_do_not_invalidate_a_legacy_manual_layout(demo_url,page):
    page,errors=page
    sample(page,demo_url)
    page.evaluate('''() => {
      const o=data.orders[0],base=calculateNesting(o.parts,o.materialSpec,o.materialSpecs);
      o.manualLayout=FasadCuttingLayout.revise(o,base,o.parts[1].id+'#1',{x:1000,y:800});saveData();updateCuttingResults(o);
    }''')
    saved=page.evaluate('JSON.stringify(data.orders[0].manualLayout)')
    panel=page.locator('#mapLayoutSettings')
    panel.locator('[data-snap=tolerance]').fill('65')
    panel.locator('[data-snap=enabled]').uncheck()
    panel.locator('[data-layout-apply]').click()
    page.reload()
    assert page.evaluate('JSON.stringify(data.orders[0].manualLayout)') == saved
    assert float(page.locator('#cuttingMaps [data-layout-key*="-P2#1"]').get_attribute('data-x')) == 1000
