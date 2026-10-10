/* Copyright (C) 2018 Olivier Goffart <ogoffart@woboq.com>

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
associated documentation files (the "Software"), to deal in the Software without restriction,
including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial
portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT
NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES
OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
*/
use std::cell::RefCell;
use qmetaobject::*;

#[test]
fn connect_rust_signal() {
    #[derive(QObject, Default)]
    struct Foo {
        base: qt_base_class!(trait QObject),
        my_signal: qt_signal!(xx: u32, yy: String),
        my_signal2: qt_signal!(yy: String),
    }

    let f = RefCell::new(Foo::default());
    let obj_ptr = unsafe { QObjectPinned::new(&f).get_or_create_cpp_object() };
    let mut result = None;
    let mut result2 = None;
    let mut con = unsafe {
        connect(
            obj_ptr,
            f.borrow().my_signal.to_cpp_representation(&*f.borrow()),
            |xx: &u32, yy: &String| {
                result = Some(format!("{} -> {}", xx, yy));
            },
        )
    };
    assert!(con.is_valid());

    let con2 = unsafe {
        connect(
            obj_ptr,
            f.borrow().my_signal2.to_cpp_representation(&*f.borrow()),
            |yy: &String| {
                result2 = Some(yy.clone());
            },
        )
    };
    assert!(con2.is_valid());

    f.borrow().my_signal(12, "goo".into());
    assert_eq!(result, Some("12 -> goo".to_string()));
    f.borrow().my_signal(18, "moo".into());
    assert_eq!(result, Some("18 -> moo".to_string()));
    con.disconnect();
    f.borrow().my_signal(25, "foo".into());
    assert_eq!(result, Some("18 -> moo".to_string())); // still the same as before as we disconnected

    assert_eq!(result2, None);
    f.borrow().my_signal2("hop".into());
    assert_eq!(result2, Some("hop".into()));
    assert_eq!(result, Some("18 -> moo".to_string())); // still the same as before as we disconnected
}

#[test]
fn connect_cpp_signal() {
    #[derive(QObject, Default)]
    struct Foo {
        base: qt_base_class!(trait QObject),
    }

    let f = RefCell::new(Foo::default());
    let obj_ptr = unsafe { QObjectPinned::new(&f).get_or_create_cpp_object() };
    let mut result = None;
    let con = unsafe {
        connect(obj_ptr, <dyn QObject>::object_name_changed_signal(), |name: &QString| {
            result = Some(name.clone());
        })
    };
    assert!(con.is_valid());
    (&*f.borrow() as &dyn QObject).set_object_name("YOYO".into());
    assert_eq!(result, Some("YOYO".into()));
}

#[test]
fn with_life_time() {
    #[derive(QObject, Default)]
    struct WithLT<'a> {
        base: qt_base_class!(trait QObject),
        _something: Option<&'a u32>,
        my_signal: qt_signal!(xx: u32, yy: String),
        my_method: qt_method!(
            fn my_method(&self, _x: u32) {}
        ),
        my_property: qt_property!(u32),
    }

    #[derive(QObject, Default)]
    struct WithWhereClose<T>
    where
        T: Clone + 'static,
    {
        #[qt_base_class = "QObject"] // FIXME
        base: QObjectCppWrapper,
        _something: Option<T>,
    }
}
