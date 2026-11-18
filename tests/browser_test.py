import socket
from threading import Thread

from fastapi import FastAPI
from playwright.sync_api import expect, sync_playwright
from uvicorn import Config, Server

from conftest import Tracker


def test_create_and_publish_offer_in_chromium(app: FastAPI, tracker: Tracker) -> None:
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        port = listener.getsockname()[1]
        server = Server(Config(app, log_level='warning'))
        worker = Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
        worker.start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                page = browser.new_page(viewport={'width': 1240, 'height': 850})
                page.goto(f'http://127.0.0.1:{port}/')
                page.get_by_role('main').get_by_role(
                    'link',
                    name='Создать кампанию',
                ).click()
                page.get_by_label('Название кампании').fill('browser_check')
                page.get_by_label('Гео-код страны').fill('AU')
                page.get_by_label('ID оффера Keitaro').fill('100')
                page.get_by_role('button', name='Создать кампанию').click()
                expect(
                    page.get_by_role('heading', name='test_kryvanos_browser_check')
                ).to_be_visible()
                expect(
                    page.get_by_text('Клики сегодня', exact=False).last
                ).to_contain_text('17')
                page.get_by_role('button', name='Добавить оффер').click()
                dialog = page.get_by_role('dialog')
                dialog.get_by_role('searchbox').fill('101')
                dialog.get_by_role('button', name='Найти').click()
                dialog.get_by_role('button', name='Добавить', exact=True).click()

                expect(page.get_by_text('Черновик', exact=True)).to_be_visible()
                expect(page.locator('progress[value="50"]')).to_have_count(2)
                assert tracker.offer_writes == 0
                page.reload()
                expect(page.get_by_text('Черновик', exact=True)).to_be_visible()
                page.get_by_role('button', name='Опубликовать').click()
                expect(page.get_by_text('Черновик', exact=True)).to_have_count(0)
                assert tracker.offer_writes == 1
                assert tracker.streams[tracker.flow_id]['offers'] == [
                    {'offer_id': 100, 'share': 50, 'state': 'active'},
                    {'offer_id': 101, 'share': 50, 'state': 'active'},
                ]

                page.set_viewport_size({'width': 390, 'height': 844})
                assert page.evaluate(
                    'document.documentElement.scrollWidth === window.innerWidth',
                )
                browser.close()
        finally:
            server.should_exit = True
            worker.join(timeout=10)
