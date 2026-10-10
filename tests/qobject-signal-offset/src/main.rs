use qmetaobject::*;
use std::cell::{Cell, RefCell};
use std::rc::Rc;

#[derive(QObject, Default)]
struct Probe {
    base: qt_base_class!(trait QObject),
    changed: qt_signal!(),
}
fn main() {
    let object = RefCell::new(Probe::default());
    let pinned = unsafe { QObjectPinned::new(&object) };
    let ptr = pinned.get_or_create_cpp_object();
    let count = Rc::new(Cell::new(0));
    let callback_count = count.clone();
    eprintln!("BEFORE_CONNECT: no video, stabilization, FFmpeg, MDK or OCIO present");
    let borrowed = object.borrow();
    let mut connection = unsafe { connect(ptr, borrowed.changed.to_cpp_representation(&*borrowed), move || callback_count.set(callback_count.get() + 1)) };
    assert!(connection.is_valid());
    drop(borrowed);
    object.borrow().changed();
    assert_eq!(count.get(), 1);
    connection.disconnect();
    object.borrow().changed();
    assert_eq!(count.get(), 1);
    eprintln!("PASS: one signal delivery and successful disconnect");
}
